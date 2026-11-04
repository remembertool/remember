#!/usr/bin/env bash
# Build, test and publish the REMEMBER Docker image (linux/amd64 and linux/arm64).
#
#   bash docker_image.sh preflight           check Docker, buildx and the Docker Hub login; changes nothing
#   bash docker_image.sh build [PLATFORM]    build one platform into the local Docker (default: this computer's)
#   bash docker_image.sh test [PLATFORM]     start the built image and check it end to end
#   bash docker_image.sh push                build both platforms and publish IMAGE:VERSION and IMAGE:latest
#   bash docker_image.sh verify-pushed       pull each published platform and run the same test on it
#
# PLATFORM is linux/amd64 or linux/arm64. VERSION is APP_VERSION in app.py.
# Settings: REMEMBER_IMAGE (default remembericpm/remember); REMEMBER_BENCHMARK, a benchmark
# id that test also runs end to end (for example bpic13-open-problems; default none).
# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
set -euo pipefail

cd "$(dirname "$0")"
IMAGE="${REMEMBER_IMAGE:-remembericpm/remember}"
PLATFORMS="linux/amd64,linux/arm64"
BUILDER="remember-builder"
TEST_PORT=17860
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' app.py)"

die() { echo "ERROR: $*" >&2; exit 1; }
native_platform() { case "$(uname -m)" in arm64|aarch64) echo linux/arm64 ;; *) echo linux/amd64 ;; esac; }
local_tag() { echo "remember:test-${1#linux/}"; }

check_platform() {
  case "$1" in linux/amd64|linux/arm64) ;; *) die "unknown platform '$1': use linux/amd64 or linux/arm64." ;; esac
}

check_tools() {
  command -v docker >/dev/null || die "docker not found. Install Docker Desktop: https://docs.docker.com/get-docker/"
  docker info >/dev/null 2>&1 || die "Docker is not running. Start Docker Desktop and retry."
  docker buildx version >/dev/null 2>&1 || die "docker buildx not found (it ships with Docker Desktop)."
  command -v curl >/dev/null || die "curl not found."
  command -v python3 >/dev/null || die "python3 not found (docker_smoke_test.py needs it)."
  [ -n "$VERSION" ] || die "APP_VERSION not found in app.py."
}

check_login() {
  # Docker Hub keeps the login in the credential helper named in config.json (credsStore).
  local user="${IMAGE%%/*}" helper
  helper="$(sed -n 's/.*"credsStore"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${DOCKER_CONFIG:-$HOME/.docker}/config.json" 2>/dev/null || true)"
  [ -n "$helper" ] || die "no Docker credential helper configured; log in with: docker login -u $user"
  "docker-credential-$helper" list 2>/dev/null | grep "\"https://index.docker.io/v1/\":\"$user\"" >/dev/null \
    || die "Docker is not logged in to Docker Hub as '$user'. Log in with: docker login -u $user"
  echo "Docker Hub login: $user"
}

ensure_builder() {
  # Multi-platform images need a BuildKit builder with the docker-container driver.
  if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
    echo "Creating the buildx builder '$BUILDER' (docker-container driver)."
    docker buildx create --name "$BUILDER" --driver docker-container >/dev/null
  fi
}

cmd_preflight() {
  check_tools
  check_login
  echo "Image:     $IMAGE:$VERSION and $IMAGE:latest"
  echo "Platforms: $PLATFORMS"
  if docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
    echo "Builder:   $BUILDER (exists)"
  else
    echo "Builder:   $BUILDER (build or push will create it)"
  fi
  echo "Preflight OK. Nothing was built or published."
}

cmd_build() {
  local platform="${1:-$(native_platform)}"
  check_platform "$platform"
  check_tools
  ensure_builder
  docker buildx build --builder "$BUILDER" --platform "$platform" \
    --label "org.opencontainers.image.version=$VERSION" \
    --tag "$(local_tag "$platform")" --load .
  docker image ls "$(local_tag "$platform")"
}

smoke() {
  local image="$1" platform="$2" name="remember-smoke-$$" start stop_start
  docker image inspect "$image" >/dev/null 2>&1 || die "image $image not found locally."
  [ "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image")" = "$platform" ] \
    || die "$image is not a $platform image."
  docker run -d --name "$name" --platform "$platform" -p "127.0.0.1:$TEST_PORT:7860" "$image" >/dev/null
  trap "docker rm -f $name >/dev/null 2>&1 || true" EXIT

  start=$(date +%s)
  until curl -fsS "http://127.0.0.1:$TEST_PORT/api/ping" >/dev/null 2>&1; do
    if [ $(( $(date +%s) - start )) -gt 180 ]; then docker logs "$name"; die "no answer on port $TEST_PORT after 180 s."; fi
    sleep 1
  done
  echo "== $image ($platform): server ready after $(( $(date +%s) - start )) s"
  # docker logs can lag behind the server for a moment; grep reads all of it (no -q: with
  # pipefail, an early exit of grep -q can fail the pipeline through SIGPIPE).
  start=$(date +%s)
  until docker logs "$name" 2>&1 | grep "Ready: http://localhost:7860" >/dev/null; do
    [ $(( $(date +%s) - start )) -gt 10 ] && die "the start-up message does not show http://localhost:7860."
    sleep 0.5
  done
  echo "Image size: $(( $(docker image inspect --format '{{.Size}}' "$image") / 1000000 )) MB (uncompressed)"
  docker exec "$name" sh -c 'echo "Java: $(java -version 2>&1 | head -1)"; echo "User: $(id -un)"; echo "XES split files in the image: $(find data -name "*.xes.gz" | wc -l)"'

  python3 docker_smoke_test.py --url "http://127.0.0.1:$TEST_PORT" ${REMEMBER_BENCHMARK:+--benchmark "$REMEMBER_BENCHMARK"}
  docker exec "$name" python verify_sample.py

  stop_start=$(date +%s)
  docker stop "$name" >/dev/null
  docker logs "$name" 2>&1 | grep "Stopped." >/dev/null || die "the server did not stop cleanly on docker stop."
  echo "PASS  docker stop ends the server cleanly in $(( $(date +%s) - stop_start )) s"
  docker rm -f "$name" >/dev/null
  trap - EXIT
}

cmd_test() {
  local platform="${1:-$(native_platform)}"
  check_platform "$platform"
  check_tools
  docker image inspect "$(local_tag "$platform")" >/dev/null 2>&1 \
    || die "$(local_tag "$platform") not found. Build it first: bash docker_image.sh build $platform"
  smoke "$(local_tag "$platform")" "$platform"
}

cmd_push() {
  check_tools
  check_login
  ensure_builder
  docker buildx build --builder "$BUILDER" --platform "$PLATFORMS" \
    --label "org.opencontainers.image.version=$VERSION" \
    --tag "$IMAGE:$VERSION" --tag "$IMAGE:latest" --push .
  docker buildx imagetools inspect "$IMAGE:$VERSION"
}

cmd_verify_pushed() {
  local platform
  check_tools
  for platform in ${PLATFORMS//,/ }; do
    docker pull --quiet --platform "$platform" "$IMAGE:$VERSION" >/dev/null
    smoke "$IMAGE:$VERSION" "$platform"
  done
  echo "Both published platforms of $IMAGE:$VERSION passed."
}

case "${1:-}" in
  preflight)     cmd_preflight ;;
  build)         cmd_build "${2:-}" ;;
  test)          cmd_test "${2:-}" ;;
  push)          cmd_push ;;
  verify-pushed) cmd_verify_pushed ;;
  *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac

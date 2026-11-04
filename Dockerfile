# SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GNU GPL v3, section 7): see the file NOTICE.
# REMEMBER as a Docker image: the web tool, the Java engine, the bundled example and
# the paper benchmark splits. The server starts with the container:
#   docker run --rm -p 127.0.0.1:7860:7860 remembericpm/remember
# then open http://localhost:7860. Build, test and publish with docker_image.sh.
#
# Base images are pinned by digest (multi-arch indexes, linux/amd64 and linux/arm64):
#   eclipse-temurin:21-jdk       -> Temurin JDK 21.0.12.1+1 (only to build the Java runtime)
#   python:3.13-slim-bookworm    -> Python 3.13.18 on Debian 12
FROM eclipse-temurin:21-jdk@sha256:5d90b26c0784ccf55af55f97cbcf7f3969c66a06299c93bdc72649219942a48f AS jre

# A Java runtime with only the modules the engine uses
# (jdeps --print-module-deps engine/*.jar -> java.base, jdk.httpserver).
RUN jlink --add-modules java.base,jdk.httpserver \
          --strip-debug --no-man-pages --no-header-files --generate-cds-archive \
          --output /opt/jre

FROM python:3.13-slim-bookworm@sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f

LABEL org.opencontainers.image.title="REMEMBER" \
      org.opencontainers.image.description="Stochastic conformance checking with Variable-Length Markov Chains: web tool, engine, example and paper benchmarks" \
      org.opencontainers.image.authors="Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi" \
      org.opencontainers.image.source="https://github.com/remembertool/remember" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

ENV JAVA_HOME=/opt/java/openjdk \
    PATH=/opt/java/openjdk/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    REMEMBER_HOST=0.0.0.0 \
    REMEMBER_PORT=7860

COPY --from=jre /opt/jre /opt/java/openjdk

WORKDIR /app
COPY requirements.txt .
# The test suites of numpy and pandas (about 50 MB) are not needed to run REMEMBER.
RUN pip install --only-binary=:all: -r requirements.txt \
 && find /usr/local/lib/python3.13/site-packages/numpy /usr/local/lib/python3.13/site-packages/pandas \
         -type d -name tests -prune -exec rm -rf {} +

# The code stays owned by root: the app only reads it and writes to /tmp.
COPY . .
RUN useradd --system --uid 10001 --no-create-home remember
USER remember

EXPOSE 7860
# Python turns SIGINT into a clean stop, so Ctrl+C and docker stop end the server at once.
STOPSIGNAL SIGINT
CMD ["python", "app.py"]

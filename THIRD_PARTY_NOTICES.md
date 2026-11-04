# Third-party notices

## Java engine: `engine/jfitVlmc-paper.jar` and `engine/trace2ecf-paper.jar`

These two files are the Java programs of the paper's replication code. With them, REMEMBER
computes the published results. No Java build step is needed.

| | |
|---|---|
| Source | <https://github.com/bistrulli/remember> (replicability material of the paper and of the REMEMBER tool paper) |
| Original files | `scripts/jfitVlmc.jar` and `scripts/trace2ecf.jar`, added in commit `9633f46` (2025-05-27) |
| SHA-256 of the originals | `jfitVlmc.jar`: `a3a0b00e79e0f7b486db822ee31aa989fcf6717f9f6e4932b602e75d51dfdfd8`<br>`trace2ecf.jar`: `d9452565d60fa8f6d54ecd1113914d402eef17d21537dde6d2d8a7599e8d6a39` |
| SHA-256 of the files in this package | `jfitVlmc-paper.jar`: `63fad5d7614f2a5104b0b522c948ba955188f5231e314f6e2f8151c6e07632a6`<br>`trace2ecf-paper.jar`: `24bd6f3765bb5f473a3c09336b83101ee8e05a8b3f852560d2a734c336cd8e41` |
| Licence | GNU General Public License v3.0 — full text in `engine/LICENSE-GPL-3.0.txt` |
| Source code | <https://github.com/bistrulli/remember2.0> (GNU GPL v3 or later). The JARs in this package were built in 2023–2024 from an earlier version of this code. |
| Java version | runs on Java 17 or newer |

**Changes made for this package** by the REMEMBER authors in September–October 2026 (allowed by the GPL; the original files are listed above):

1. *Smaller files.* The original `jfitVlmc.jar` (53 MB) is an Eclipse "jar-in-jar" that also
   contains many libraries the engine never uses (for example MultiVeStA and ICU4J). The
   original `trace2ecf.jar` (15 MB) also contains unused libraries. The files in this package
   contain only the classes that the programs use, taken in the same class-path order as the
   original launcher, so every class is the same one that ran in the original file.
2. *One extra output column.* In `fitvlmc/fitVlmc.class` (source: `fitvlmc/fitVlmc.java`), the
   format of the likelihood file was changed from `"%f,%d\n"` to `"%f,%d,%1$.17e\n"`. The first two columns are unchanged (the
   likelihood with 6 decimals, as used for uEMSC in the paper, and the trace length). The
   third column repeats the likelihood with full precision; REMEMBER uses it only for the
   diagnostics (trace support, ER-U, predictive perplexity), never for uEMSC.

On the 11 benchmark datasets, the files of this package and the original files give
byte-identical flow graphs (`.ecf`), VLMC models (`.vlmc`) and likelihood columns.

The two JARs contain these libraries, unchanged, each under its own licence (texts in
`META-INF/licenses/` inside each JAR). The source code of the two copyleft libraries is
included in `engine/third-party-sources/`; the others can be downloaded at the addresses below.

| Library | Version | Licence | In | Source code |
|---|---|---|---|---|
| jdistlib | 0.4.5 | GNU GPL v2 (most files: version 2 or later) | engine | included: `jdistlib-0.4.5-src.jar`, the source JAR shipped inside the original `jfitVlmc.jar` · project: <https://sourceforge.net/projects/jdistlib/> |
| java-getopt | 1.0.13 | GNU LGPL v2 | both | included: `java-getopt-1.0.13-sources.jar`, from Maven Central |
| Apache Commons Math | 3.6.1 | Apache License 2.0 | engine | <https://repo1.maven.org/maven2/org/apache/commons/commons-math3/3.6.1/> |
| Apache Commons Lang | 3.9 | Apache License 2.0 | engine | <https://repo1.maven.org/maven2/org/apache/commons/commons-lang3/3.9/> |
| ANTLR 4 runtime | 4.7.2 | BSD 3-Clause | both | <https://repo1.maven.org/maven2/org/antlr/antlr4-runtime/4.7.2/> |
| Apache Commons IO | 2.10.0 | Apache License 2.0 | trace2ecf | <https://repo1.maven.org/maven2/commons-io/commons-io/2.10.0/> |

SHA-256 of the included source files: `jdistlib-0.4.5-src.jar`
`21ec64d01f7ee6e1fc709073596644096f5b409b19aba563c8cd270e954272de`, `java-getopt-1.0.13-sources.jar`
`0728c551077cbb0c4e721b95915c732642d70eef24b29ac7de549983e4f1818b`.

## Python packages

They are not included in this package. The launcher installs them from PyPI at the first
start (`requirements.txt`): Flask (BSD 3-Clause), pandas (BSD 3-Clause), NumPy
(BSD 3-Clause), and their dependencies.

## Benchmark data: `data/benchmarks/`

The split files come from the supplementary material of F. Mannhardt, S.J.J. Leemans,
C.T. Schwanen, M. de Leoni, *Modelling data-aware stochastic processes — discovery and
conformance checking* (Zenodo, DOI [10.5281/zenodo.7578655](https://doi.org/10.5281/zenodo.7578655)).
They are derived from public event logs (BPI Challenges 2012, 2013, 2017, 2020, Sepsis,
Road Traffic Fines). Please see that Zenodo record and the original log publications for
the licence terms and the citations to use.

The files in `data/benchmarks/<dataset>/paper/` contain the same splits converted to the
trace format of the paper's pipeline (`!$ activity$ … end$`). They were produced with the
conversion code of github.com/bistrulli/remember (`vlmcProcessMining.py`, with pm4py), which
keeps the order of events with equal timestamps that was used for the paper's results.

`data/benchmarks/paper_reference_results.json` contains the uEMSC values of Figs. 4 and 5
of the paper, read from the vector data of the figures.

This notice does not change the licence of the other files in this package.

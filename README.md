# REMEMBER — stochastic conformance checking with Variable-Length Markov Chains

REMEMBER is a tool for stochastic conformance checking. It implements the method of
Incerto, Vandin and Sarv Ahrabi (*Information Systems* 133, 2025). It runs on your own
computer and opens in your web browser:

1. it learns a Variable-Length Markov Chain (VLMC) from a **reference log**;
2. it scores one or more **check logs** against that VLMC;
3. it reports **uEMSC** (the main score) and three supporting measures.

The check logs are never used to learn the model. REMEMBER runs the pipeline of the paper's
replication code (<https://github.com/bistrulli/remember>) with its Java engine
(`engine/jfitVlmc-paper.jar`, `engine/trace2ecf-paper.jar`). On the paper benchmarks it
gives the published values (section 4).

---

## 1. Quick start

### What you need (only once)

| | Version | Where to get it |
|---|---|---|
| Java | 17 or newer | e.g. Temurin 21 LTS: <https://adoptium.net> |
| Python | 3.11 – 3.14 | <https://www.python.org/downloads/> |
| Internet | first start only | the launcher downloads Flask, pandas and NumPy (about 25 MB) into a private `.venv` folder |

### macOS

1. Double-click the `.zip` file to unpack it. Move the folder to a normal local folder
   (for example your home folder).
2. Double-click **`run_mac.command`**.
3. The first start takes a few minutes (installation). Then the browser opens
   at `http://127.0.0.1:7860`.
4. To stop REMEMBER, press **Control + C** in the Terminal window.

If macOS does not open the file (for example *“cannot verify the developer”* or
*“you do not have permission”*), use Terminal instead. This always works:

1. Open **Terminal** (Applications → Utilities → Terminal).
2. Type `bash ` (the word *bash* and one space). Do not press Enter yet.
3. Drag the file `run_mac.command` from Finder into the Terminal window.
4. Press **Enter**.

If Terminal asks for access to the Desktop, Documents or Downloads folder, click **OK**.

### Windows

Double-click **`run_windows.bat`**. If Windows shows *“Windows protected your PC”*,
click **More info → Run anyway**. Keep the black window open while you use REMEMBER.
To stop REMEMBER, press **Ctrl + C** in that window.

### Linux

```bash
bash run_unix.sh
```

The launcher prints the address it uses. If port 7860 is busy, it takes the next free port.

### Docker (instead of the launchers)

With Docker (<https://docs.docker.com/get-docker/>) you need neither Java nor Python. The
image `remembericpm/remember` contains the tool, Java, the bundled example and the
benchmark splits, and runs on Intel/AMD and ARM computers (Apple silicon included):

```bash
docker run --rm -p 127.0.0.1:7860:7860 remembericpm/remember:3.7
```

Then open `http://localhost:7860`. To stop REMEMBER, press **Ctrl + C** in the terminal.
With `--rm` the container is deleted when it stops. To keep a container named `remember`
that runs in the background (`docker run -d` = `docker create` + `docker start`):

```bash
docker run -d --name remember -p 127.0.0.1:7860:7860 remembericpm/remember:3.7
```

Then stop it with `docker stop remember`, start it again with `docker start remember`,
and delete it with `docker rm -f remember`.
For another port, change only the first number (`-p 127.0.0.1:8080:7860`, then open
`http://localhost:8080`). To check the image, run
`docker run --rm remembericpm/remember:3.7 python verify_sample.py`; it must end with
`All checks passed.`

The image does not contain the XES copies of the benchmark splits (about 143 MB): the
benchmarks run from the files in `paper/` (section 4), and the XES splits are on Zenodo
(DOI [10.5281/zenodo.7578655](https://doi.org/10.5281/zenodo.7578655)).

### Check the installation (optional)

After the first start, open a terminal in the package folder (macOS: type `cd `, drag the
folder into the Terminal window, press Enter) and run the command below. It must end with
`All checks passed.`

```bash
.venv/bin/python verify_sample.py              # macOS / Linux
.venv\Scripts\python.exe verify_sample.py      # Windows
```

---

## 2. Using the tool

The page has three evaluation paths:

| Path | What it does |
|---|---|
| **Your logs** | one reference log + one or more check logs |
| **Example** | `data/samples/reference.xes` + three small check logs (a quick test) |
| **Paper benchmarks** | the 11 datasets of the paper, 10 paired splits each |

### Input formats

| Format | Notes |
|---|---|
| XES, XES.GZ | `concept:name` (activity) and `time:timestamp` of each event; one trace per `<trace>`, whose `concept:name` is the case id |
| CSV, CSV.GZ | columns are found automatically, e.g. `case_id`, `activity`, `timestamp` (also `case:concept:name`, `concept:name`, `time:timestamp`); the separator (`,` `;` tab) is detected |
| TXT, TXT.GZ | activity tokens, each trace ends with `end$`. A file already in the paper's format (`!$ activity$ … end$`) is used unchanged |

**Other names.** If a log uses other names, open *Column and attribute names* under the
upload boxes and type them; empty fields keep the defaults above. The names apply to the
reference log and to the logs to check.

| Field | XES | CSV |
|---|---|---|
| Case id | attribute of the `<trace>`; if a trace does not have it, the attribute of each event, so events can also be grouped by an event attribute | column name |
| Activity | attribute of each event | column name |
| Timestamp | attribute of each event | column name |

A name that is not in the file gives an error that lists the names found. CSV column names
may differ in upper/lower case, spaces and punctuation (`Case ID` finds `case_id`); XES keys
must match exactly.

- Only the control flow is used (case, activity, order of events).
- Events are ordered by timestamp inside each case. Events with the same timestamp keep
  their file order. Without a timestamp column (CSV), the row order is used and the page
  shows a notice.
- Activity names are cleaned as in the paper's code: the characters
  `space _ & $ ( ) { } [ ] - + . ; '` are removed (so *Send Fine* and *Send-Fine* become the
  same activity, as in the paper). If a name still contains other characters (for example
  `/` or `é`), they are removed and a short code is added, so different names stay different.

### Model setting

There is **no parameter to choose**. The VLMC is learned with the setting of the paper's
experiments: **no pruning** (the engine keeps every context that the reference log
supports).

---

## 3. Reported values

| Value | Meaning | Better |
|---|---|---|
| **uEMSC** | main stochastic conformance score, computed as in the paper's code (below); 1 = full agreement | higher |
| **ER-U** | Entropic Relevance with uniform background (Alkhammash et al., 2022), bits per trace | lower |
| **Predictive perplexity** | next-activity prediction diagnostic, only on traces with non-zero likelihood | lower |
| **Trace support** | share of check-log traces with non-zero likelihood under the VLMC | higher |

- uEMSC = 1 − Σ max(L(t) − M(t), 0) over the distinct traces t of the check log, where
  L(t) is the frequency of t in the check log and M(t) its likelihood in the VLMC. As in the
  paper's code, both values are rounded to 6 decimals.
- With several check logs, the cards show the **unweighted mean** over the check logs.
- For a benchmark, uEMSC is shown as **mean ± sample standard deviation (n − 1)** over
  the 10 splits. Every split is also listed in the table.
- **Download results (CSV)** saves the table.
- Times are wall-clock times on your computer (they include the start of Java). Do not use
  them to compare methods.
- Click or point at the **ⓘ** next to a measure to see its definition.

---

## 4. Paper benchmarks

`data/benchmarks/` contains the 11 datasets of the paper, each with 10 paired, about
50/50 random splits (`split_XX_reference.xes.gz` and `split_XX_check.xes.gz`). The splits
are the ones of the paper, taken from the supplementary material of Mannhardt et al.
(DOI [10.5281/zenodo.7578655](https://doi.org/10.5281/zenodo.7578655)); they are
byte-identical to the splits in the paper's replication code.
For every split, a new VLMC is learned from the reference part, and the check part
is scored.

### Events with the same timestamp

Some traces contain events with **the same timestamp** (for example several lab tests in
Sepsis). The paper's code (`vlmcProcessMining.py`) sorted the events with pandas' default
sort, which is not stable, so the order of such events depends on the computer. The folder
`paper/` of each dataset therefore contains the same splits already converted by the paper's
code, with the event order of the paper's results (`split_XX_reference.txt.gz`,
`split_XX_check.txt.gz`). With these files every computer gives the published values. If the
folder is missing, REMEMBER converts the XES files itself (events with equal timestamps keep
their file order), some values can differ slightly, and the page shows a notice.

### Reference outputs

SD = sample standard deviation over the 10 splits. The values are those of Figs. 4 and 5
of the paper:

| Dataset | uEMSC (mean ± SD) | Paper, VLMC mean | Figure | ER-U (bits/trace) |
|---|---:|---:|---|---:|
| BPIC12-A | 0.9776 ± 0.0052 | 0.9776 | Fig. 4(a) | 2.848 |
| BPIC13 Incidents | 0.6523 ± 0.0061 | 0.6523 | Fig. 4(b) | 23.927 |
| BPIC13 Open Problems | 0.6930 ± 0.0113 | 0.6930 | Fig. 4(c) | 7.544 |
| BPIC13 Closed Problems | 0.7249 ± 0.0113 | 0.7249 | Fig. 4(d) | 9.714 |
| BPIC17 Offer Log | 0.9900 ± 0.0027 | 0.9900 | Fig. 4(e) | 2.187 |
| BPIC20 Domestic Declarations | 0.9675 ± 0.0076 | 0.9675 | Fig. 4(f) | 2.867 |
| BPIC20 International Declarations | 0.8160 ± 0.0062 | 0.8160 | Fig. 4(g) | 12.850 |
| BPIC20 Prepaid Travel Cost | 0.8380 ± 0.0132 | 0.8380 | Fig. 4(h) | 9.046 |
| BPIC20 Request for Payment | 0.9598 ± 0.0059 | 0.9598 | Fig. 5(i) | 3.027 |
| Sepsis | 0.1648 ± 0.0093 | 0.1648 | Fig. 5(j) | 58.791 |
| Road Traffic Fines | 0.9901 ± 0.0018 | 0.9901 | Fig. 5(k) | 2.752 |

Run time: VLMCs are learned without pruning, as in the paper, so the models are large. On a
2-core machine one dataset took between about 15 seconds (BPIC13 Open Problems) and about
20 minutes (Road Traffic Fines); all 11 datasets together took about 50 minutes. A normal
laptop is faster.

### Comparison with the paper

After a benchmark run, the report shows a **Comparison with the paper** section:

- **This dataset** — your live result next to the VLMC result published in the paper and
  the 8 competitor techniques of the paper (box plots over the 10 splits, sorted by mean
  uEMSC, with your rank and the gap to the best competitor). This matters most for logs
  where every method has a low uEMSC, such as Sepsis: there VLMC (0.165) is low in
  absolute terms but about 3.7× the best competitor (0.045).
- **All 11 datasets** — VLMC against the best competitor on every dataset. In the paper,
  VLMC is best on 10 of 11 datasets; the exception is BPIC13 Open Problems.
- **Download comparison (CSV)** saves all published values and your live runs.

The published values are in `data/benchmarks/paper_reference_results.json`. They were read
from the vector drawing data of Figs. 4 and 5 of the paper (accuracy about ±0.001). In
those figures the line in each box is the **mean** of the 10 splits; for the three
techniques of Leemans et al. (2024) the paper gives only the mean.

Run the benchmarks without the browser (from the package folder). The output also lists
the published VLMC value and the best competitor of the paper:

```bash
.venv/bin/python benchmark_runner.py                          # list the datasets
.venv/bin/python benchmark_runner.py sepsis                   # one dataset
.venv/bin/python benchmark_runner.py all --csv results.csv    # all 11 datasets
```

(On Windows use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.)

---

## 5. Example: reference results

The bundled example gives (also stored in `data/samples/expected_results.csv`, and checked
by `verify_sample.py`):

| Check log | uEMSC | ER-U (bits/trace) | Predictive perplexity | Trace support |
|---|---:|---:|---:|---:|
| `check_1.xes` | 0.986666 | 1.404394 | 1.214935 | 30/30 |
| `check_2.xes` | 0.773334 | 1.691551 | 1.264275 | 30/30 |
| `check_3.xes` | 0.566666 | 9.053966 | 1.240718 | 17/30 |

These values check that the installation works. They are not a scientific ground truth.

---

## 6. How REMEMBER prepares the logs

As in the paper's code, every trace is written as

```text
!$ activity_1$ activity_2$ ... end$
```

- `!$` starts every trace. The engine uses it as the first context, so the probability of
  the first activity is part of the trace likelihood. `end$` closes the trace.
- Events are ordered by timestamp; cases follow the sorted order of their case id.
- Activity names are cleaned as described in section 2.

For every check log, REMEMBER computes the likelihood M(t) of each distinct trace t with
the learned VLMC (the engine prints it with 6 decimals, as in the paper) and the frequency
L(t) of t in the log, and then uEMSC = 1 − Σ max(round(L(t), 6) − round(M(t), 6), 0).
ER-U, predictive perplexity and trace support use the same likelihoods with full precision;
they never change uEMSC.

---

## 7. Troubleshooting

| Message or problem | What to do |
|---|---|
| *Java 17 or newer was not found* | Install Java 17+ (e.g. Temurin 21 from <https://adoptium.net>) and start again. To see which Java is found, run `python3 java_runtime.py` in the package folder (Windows: `py java_runtime.py`). |
| *Python 3.11 or newer was not found* | Install Python from <https://www.python.org/downloads/> (Windows: tick *Add python.exe to PATH*). |
| *Package installation failed* | Check the internet connection and start again. |
| The browser does not open | Open the address printed in the window (normally `http://127.0.0.1:7860`). |
| The page shows an error after an update | An older REMEMBER window may still be running with the old code. Close every REMEMBER window (Ctrl + C), then start again. |
| Something is broken after an update | Delete the `.venv` folder and start again. |

Uploaded files are copied only to a temporary folder and deleted after each run.
REMEMBER listens only on `127.0.0.1`, so other computers cannot connect to it. With Docker,
the `127.0.0.1:` in the `-p` option does the same.

---

## 8. Package contents

| File / folder | Purpose |
|---|---|
| `run_mac.command`, `run_unix.sh`, `run_windows.bat` | launchers |
| `app.py` | local web interface (Flask) |
| `remember_engine.py` | runs the pipeline of the paper (Java engine + uEMSC) |
| `trace_io.py` | reads XES / CSV / TXT logs |
| `metrics.py` | ER-U, predictive perplexity, trace support |
| `benchmark_runner.py` | paper benchmarks (page and command line) |
| `java_runtime.py` | finds Java 17+ |
| `verify_sample.py` | installation check |
| `templates/`, `static/` | web page |
| `data/samples/` | bundled example and expected results |
| `data/benchmarks/` | 11 datasets × 10 splits (XES, and in `paper/` the same splits in the paper's event order), `benchmark_manifest.json`, and `paper_reference_results.json` (published results for the comparison) |
| `engine/` | Java engine of the paper (`jfitVlmc-paper.jar`, `trace2ecf-paper.jar`), its licence, and in `third-party-sources/` the source code of its copyleft libraries |
| `LICENSE`, `NOTICE` | GNU General Public License v3, and the copyright notice with the additional terms |
| `CITATION.cff` | citation metadata (authors, licence, paper) for GitHub, Zenodo and reference managers |
| `THIRD_PARTY_NOTICES.md` | origin and licences of the engine and the data |
| `Dockerfile`, `docker_image.sh`, `docker_smoke_test.py` | Docker image: `bash docker_image.sh` lists the commands to build, test and publish it |

---

## Licence

REMEMBER — Copyright © 2026 Emilio Incerto¹, Andrea Vandin²˒³, Sima Sarv Ahrabi²

¹ IMT Lucca, Italy · ² L'EMbeDS and Institute of Economics, Sant'Anna School for Advanced
Studies, Pisa, Italy · ³ DTU Technical University of Denmark, Kongens Lyngby, Denmark

REMEMBER is free software: you can redistribute it and/or modify it under the terms of the
GNU General Public License as published by the Free Software Foundation, either version 3
of the License, or (at your option) any later version.

REMEMBER is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details: file `LICENSE`, also shown by the
*Licence* link on the page.

**Additional terms** (GNU GPL v3, section 7; full text in `NOTICE`): a modified version must
not be distributed under the name "REMEMBER", and the licence grants no trademark rights for
the name or the logo. You may still say that your work is based on REMEMBER.

The Java engine and the benchmark data keep their own licences; see
`THIRD_PARTY_NOTICES.md`, which also says where to find the source code of the engine and of
its libraries.

---

## Citing REMEMBER

The **Cite us** button at the top of the page shows the reference and the BibTeX entry, with
copy buttons.
The same metadata are in `CITATION.cff`, which GitHub and Zenodo read automatically.

```bibtex
@article{DBLP:journals/is/IncertoVA25,
  author       = {Emilio Incerto and
                  Andrea Vandin and
                  Sima Sarv Ahrabi},
  title        = {Stochastic conformance checking based on variable-length Markov chains},
  journal      = {Inf. Syst.},
  volume       = {133},
  pages        = {102561},
  year         = {2025},
  url          = {https://doi.org/10.1016/j.is.2025.102561},
  doi          = {10.1016/J.IS.2025.102561},
  timestamp    = {Tue, 24 Mar 2026 08:46:40 +0100},
  biburl       = {https://dblp.org/rec/journals/is/IncertoVA25.bib},
  bibsource    = {dblp computer science bibliography, https://dblp.org}
}
```

---

## References

- E. Incerto, A. Vandin, S. Sarv Ahrabi. *Stochastic conformance checking based on
  variable-length Markov chains.* Information Systems 133 (2025) 102561.
  <https://doi.org/10.1016/j.is.2025.102561>
- Replication package of the paper: <https://doi.org/10.5281/zenodo.13348234>
- F. Mannhardt, S.J.J. Leemans, C.T. Schwanen, M. de Leoni. *Modelling data-aware
  stochastic processes — discovery and conformance checking.* In: Application and Theory
  of Petri Nets and Concurrency (PETRI NETS 2023), Springer, pp. 77–98.
  Supplementary material: <https://doi.org/10.5281/zenodo.7578655>
- H. Alkhammash, A. Polyvyanyy, A. Moffat, L. García-Bañuelos. *Entropic relevance:
  A mechanism for measuring stochastic process models discovered from event data.*
  Information Systems 107 (2022) 101922.

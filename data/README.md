# Triage experiment data

`triage.html` (repo root) is the YouTube prototype's five-page flow, prefilled from these files with two scenarios: triage channel and advice message.

Open `triage.html` directly, or serve the repo root (`python3 -m http.server 8765`) to read the JSON live. Opened from disk it reads `bundle.js`, so run `python3 scripts/build_bundle.py` after editing any file here.

| File | Holds | Page it fills |
|---|---|---|
| `experiment.json` | Stages, services, metrics, validity checks | Treatments, Results |
| `versions/*.txt` | One text file per version, the thing a participant or agent is given | Treatments |
| `triage_arms.json` | Scenario 1 version list: id, type, file, group, hypothesis; fixed engine | Treatments |
| `form_questions.json` | Question bank that `build_versions.py` turns into `versions/F0–F3.txt` | Treatments |
| `messages.json` | Scenario 2 versions (M0–M6) and message components | Treatments |
| `vignettes.json` | 15 hidden cases: fact sheet, correct service, per-case advice text | Participants |
| `profiles.json` | 6 behaviour variables and the participant prompt | Participants |
| `actions.json` | Allowed moves and follow-up questions per group | Actions |
| `results/` | Result files listed in `index.json`. `MOCK_results.json` is not model output | Results |

Scripts: `build_versions.py` regenerates the form text files, `validate_data.py` cross-checks the files, `make_mock_results.py` regenerates the mock, `build_bundle.py` rebuilds `bundle.js`.

Deep links for demos: `triage.html#/results?scn=message&preset=nudge&split=nhs_trust`, `triage.html#/dataset?open=F1&case=E1`.

## On the platform prototype (`index.html`)

`scripts/build_platform_runs.py` turns this experiment into two runs in the platform's own shape and writes `data/triage-runs.js`, which `index.html` loads. They appear on the home page as "Which 111 substitute triages best?" and "Which advice message gets followed?".

| Here | On the platform |
|---|---|
| triage arms, message arms | versions, each a text file; Form, Chat prompt, Call script and Direct question are separate types, and a version is one of them |
| profile axes, vignettes | participant variables; the vignette is the hidden "Condition" variable |
| right / too low / too high / gave up, moves per version type | actions, limited to types |
| triage engine and the 10 services | the judge on the Actions page |
| follow-ups, miss tags, reason codes | follow-up questions and grouped reasons |
| validity anchors, segment gaps | notes on each version's results page |

Rebuild after changing data: `python3 scripts/make_mock_results.py && python3 scripts/build_platform_runs.py`. Results are mock.

## Running a real experiment ("+ New scenario")

"+ New scenario" on the home page makes a real experiment: your own versions and participant splits, answered by a Claude model. "+ Demo" makes the mock one, with the Upload dataset buttons and prepared results; it carries a Demo tag.

A real run goes through the local server, which calls the `claude` command in print mode (`claude -p`), so it uses the Claude subscription you are logged in to. No API key is involved.

    python3 scripts/serve.py

Then open http://localhost:8765/index.html. The Run page says whether `claude` is reachable and how many calls the run makes: participants × versions × runs × (1 + follow-up questions). Each call takes a few seconds and counts against your subscription's usage limits, so start small; new real scenarios default to 30 participants.

Each participant is one `claude -p` session: the first call is their reaction, and every follow-up question resumes that session as a fork, in parallel. Tools, settings, hooks and CLAUDE.md are switched off for these calls, and the sessions are deleted afterwards.

`STANDIN_FAKE=1 python3 scripts/serve.py` runs the same flow with random answers and no model, to test the page for free.

## Control set (real patients)

`data/control/` holds a control built from one open dataset, extended where it has gaps.

- **Source:** Moon S-H, Shim JL, Park K-S, Park C-S (2019), *Triage accuracy and causes of mistriage using the Korean Triage and Acuity Scale*, PLOS ONE 14(9): e0216972, CC BY 4.0. 1,267 adult records from two Korean emergency departments. `moon2019_ktas.csv` is the copy published on Kaggle ("Emergency Service - Triage Application").
- **Build:** `python3 scripts/build_control.py`, then `python3 scripts/build_platform_runs.py`.
- **On the platform:** these patients are the main run, "Which 111 substitute triages best?". One experiment in two stages. Stage 1, Triage: four forms and three chats against the real nurse (control), on all 1,267 patients; scores are right level, too low, too high, gave up. Stage 2, Closing message: seven messages on the 733 patients whose right level is 1 to 3, who are all told to go to emergency care; scores are went as told, did not go. The simulated 111 call and "no tool" are left out of this run. The earlier run on 17 written conditions is kept behind the "Show authored cases run" switch on the home page.

| | What | Where it comes from |
|---|---|---|
| Real | sex, age, arrival, injury, recorded complaint, alertness, pain score, vital signs, diagnosis, the nurse's level, the expert panel's level, the cause of a nurse's error | the record, unchanged |
| Derived | the patient's opening words and fact sheet | a fixed rule per real field, named in each fact's `from` (pain from the pain score, fever from temperature, breathlessness from breathing rate or oxygen, racing heart from pulse, faintness from blood pressure) |
| Synthetic | reporting style, health literacy, English, digital confidence | drawn at random, as in the main run |
| Mock | every result for our own versions | sampled from assumed effects; no model was run |

The nurse rows reproduce the paper: 1,081 of 1,267 agree with the experts (85.3%), 131 too low, 55 too high.

Limits to state when presenting:

- **Assumption, no measurements:** for the 147 patients whose record shows an abnormal vital sign, a version that cannot measure anything is assumed to give a level one step too low 60% of the time (`UNSEEN` in `build_control.py`).
- **Assumption, advice routes:** each message names an NHS route for the patient's right level: level 1 to 999, levels 2 and 3 to A&E, level 4 to an urgent treatment centre, level 5 to a GP (`ROUTE` in `build_control.py`).
- Everyone went to an emergency department, so there are no pharmacy or self-care cases.
- The nurse saw the patient and measured vital signs; a form or chat gets only what the patient says.
- The right answer is a KTAS level (1 to 5), not an NHS service. The NHS route shown beside each level is our mapping.
- Onset, duration, history and medicines are not in the published file, so the fact sheets leave them out.
- Some recorded complaints were lost in the published file (Korean text saved as question marks); those patients open with a generic line.
- The file gives a cause code for each nurse error, but the paper's text describes only two of them (pain score, symptoms misjudged); the rest are shown as "other recorded cause".

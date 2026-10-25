# Ghost Data Still Exists — Deletion Audit Agent

For every request in `dataset/deletion_requests.csv` the agent decides whether deletion was actually
requested, finds every copy of the person's data across systems, reconstructs each record's state at
`audit_at`, applies `dataset/deletion_rules.csv`, and writes `output.csv`
(`case_id,deletion_status,steps_json`) at the repository root.

## Setup

Python 3.10+. Place this folder as `code/` in the challenge repository, next to `dataset/`.

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1      macOS/Linux: source .venv/bin/activate
python -m pip install -r code/requirements.txt
```

Optional: Tesseract OCR (`tesseract` on PATH) is needed only to re-read screenshots. The extracted text
of all 15 PDFs/screenshots ships in `code/cache/document_text.json`, so runs are identical without it.
No API keys or network access are required.

## Run (from the repository root)

```bash
python code/main.py                        # 518 evaluation requests -> output.csv
python code/main.py --samples              # 32 samples -> code/evaluation/sample_predictions.csv
python code/evaluation/evaluate.py -v      # metrics vs dataset/sample_output.csv
python code/evaluation/custom_cases.py     # 6 custom evaluation scenarios
python code/evaluation/validate_output.py  # output.csv against the output contract
python -m pytest code/tests -q             # 59 tests
```

If scipy is unavailable the activity matcher falls back to greedy assignment (with a warning); install
`code/requirements.txt` for the exact submitted results.

On Windows set `$env:PYTHONUTF8 = "1"` first so non-English text prints correctly.

## How it works

```
request_text ─► auditor/intent.py     clause-level, multilingual: does this authorise deletion?
users files  ─► auditor/identity.py   current + historical e-mails, phones, hashes, user ids (exact match)
evidence     ─► auditor/evidence.py   SQL replicas, JSON exports, text handovers  ┐ observations:
             ─► auditor/logs.py       8 log formats, trace-id linking              │ record, system, category,
             ─► auditor/artefacts.py  PDFs + screenshots (documents.py: pypdf,     │ present?, PII?, flow on?,
                                      Tesseract) with corroborated OCR repair      ┘ restore allowed?, identifiers
activity     ─► auditor/activity.py   links identifier-free records through deletion bursts
                                      (fixed timing phase, optimal Hungarian assignment)
                  auditor/engine.py   per case: linked records -> state at audit_at -> policy
                  auditor/policy.py   rules -> findings, remediation, verification (ordered)
                  auditor/checks.py   diagnostics -> evaluation/subject_checks.csv
```

Principles:

- **Claims are not proof.** Workflow statuses, worker results and catalogue links never decide state;
  captured records do.
- **Time discipline.** Only captures at or before `audit_at` decide state or are cited. A capture up to
  7 days later may only name a retained record. Screenshots and catalogue links count only within
  7 days before the request.
- **Replicas.** The newest capture wins; any replica copy still present keeps the record alive.
- **Identity.** Exact, case-insensitive identifiers; names are never used. Look-alikes, unknown or
  ambiguous e-mails never authorise deletion. OCR e-mails are repaired only when corroborated.
- **Policy.** Tombstones keep the stable reference and lose direct identifiers. Legal holds and security
  audit records are retained (`VERIFY_RECORD_PRESENT`) and never deleted. Flows and restores are stopped
  before records are changed.

The final run uses no language model (0 tokens); see `evaluation/usage_report.md`. Metrics, custom
cases, failures and improvements are in `evaluation/evaluation_report.md`.

## Layout

```
main.py                      entry point
auditor/                     pipeline modules
evaluation/                  evaluate.py, custom_cases.py, reports, diagnostics CSVs
tests/                       pytest suite
cache/document_text.json     extracted PDF / screenshot text
requirements.txt
```

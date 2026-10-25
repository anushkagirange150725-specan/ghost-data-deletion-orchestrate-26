# Evaluation Report — Ghost Data Still Exists

Deterministic deletion-audit pipeline (`code/main.py`). All numbers below come from the final code.

```
python code/main.py --samples          # 32 public samples -> code/evaluation/sample_predictions.csv
python code/evaluation/evaluate.py -v  # metrics against dataset/sample_output.csv
python code/evaluation/custom_cases.py # 6 custom scenarios
python code/evaluation/validate_output.py   # output contract check (0 violations)
python -m pytest code/tests -q         # 59 unit / property tests
```

## 1. Results on the 32 public samples

| Metric | Value |
|---|---|
| Case-level deletion-status accuracy | **1.000** (32/32) |
| Exact-row accuracy (status + every step, in order) | **0.906** (29/32) |
| Sequence accuracy (same steps in the same order: phase, system, resource, operation) | **0.906** |
| Step precision / recall / F1 (all six step fields must match) | **1.000 / 0.979 / 0.990** |
| Well-formed rows (step_no 1..n, phases never go backwards) | **1.000** |

Field-level accuracy, comparing step *i* with gold step *i* (extra or missing positions count as misses):

| phase | system_id | resource_id | operation | state | evidence_id |
|---|---|---|---|---|---|
| 0.979 | 0.959 | 0.959 | 0.959 | 0.959 | 0.979 |

Precision is 1.000: every step the agent emits is correct. The 3 imperfect rows all miss steps for
resources that appear in **no participant-visible file**:

| Case | Missing gold step | Why it cannot be produced honestly |
|---|---|---|
| case_04 | `account_004` VERIFY_ABSENT, `analytics_901` VERIFY_ANONYMIZED | neither id occurs in any evidence file, activity row or log |
| case_18 | `audit_record_6645` VERIFY_PRESENT | id occurs nowhere in the dataset |
| case_20 | `audit_record_5569` VERIFY_PRESENT | id occurs nowhere in the dataset |

Inventing these ids would require organiser truth, so they are left as known misses.

## 2. Score progression (samples)

| After phase | What was added | Status | Exact rows | Step F1 |
|---|---|---|---|---|
| 3 | Identity history, SQL/JSON/text/log parsers, policy rules, step ordering | 0.969 | 0.312 | 0.907 |
| 4 | Activity-burst linking (Hungarian assignment) and snapshot scopes as proof of absence | 0.969 | 0.875 | 0.976 |
| 5 | Multilingual clause-level intent, identity safeguards (no change by design) | 0.969 | 0.875 | 0.976 |
| 6 | PDFs + screenshots (pypdf, Tesseract), safe OCR repair, catalogue labels and veto | **1.000** | **0.906** | **0.990** |

## 3. Full evaluation set (518 requests)

| Reported by workflow | Audited COMPLETE | Audited INCOMPLETE | NOT_APPLICABLE |
|---|---|---|---|
| COMPLETE (254) | 89 | **165** | 0 |
| PARTIALLY_COMPLETE (152) | 36 | 116 | 0 |
| NOT_STARTED (112) | 27 | 75 | 10 |
| **Total** | **152** | **356** | **10** |

65% of deletions the workflow called COMPLETE still leave personal data, an active flow or a restore
path at `audit_at`; 63 requests reported as not finished are in fact compliant. The output contains 3,239
steps (370 remaining records, 214 exposed-PII findings, 113 active data flows, 26 restore risks).

Claims are not proof. Comparing each deletion-worker result with the record's real state shows that the
reported result disagrees with reality about 20% of the time:

| Reported result | Record actually gone | Record actually present |
|---|---|---|
| SUCCESS | 233 | 32 |
| PARTIAL | 135 | 18 |
| FAILED | 97 | 8 |

## 4. Custom evaluation cases (`code/evaluation/custom_cases.py`) — 6/6 pass

Each scenario copies a solved sample, changes one field, re-runs the whole pipeline and checks the
answer required by the rules.

| # | Scenario | Change | Expected | Result |
|---|---|---|---|---|
| C1 | Current vs old e-mail | case_29 filed from the user's current address | identical to gold case_29 | PASS |
| C2 | Same intent, other language | case_21 text in German | identical to gold case_21 | PASS |
| C3 | Forged account, "do not delete yet" | case_21 asks to keep the account for a police report | NOT_APPLICABLE, [] | PASS |
| C4 | Look-alike e-mail | case_28 filed from `smartinez6461.jr@gmail.com` (a stranger's record) | NOT_APPLICABLE, user_28 never touched | PASS |
| C5 | Messy but exact e-mail | case_31 as `mailto:A.EZE08@GMAIL.COM ` | identical to gold case_31 | PASS |
| C6 | Time discipline | case_24 `audit_at` moved before evidence_92 was captured | no step cites later evidence | PASS |

C4 and C5 failed before the Phase 5 identity safeguards (the look-alike produced COMPLETE with no
steps; `mailto:` did not resolve).

## 5. Failures found and improvements made

| Failure found | Fix | Effect |
|---|---|---|
| Records with no identifiers left (anonymised analytics, 404 profiles) could not be linked | Activity bursts: anchor on the primary-profile delete; policy follow-ups land 15–75 min later at a fixed seconds-phase (9–11 s mod 30), result checks 75–210 min later (20–22 s mod 30); optimal Hungarian matching across all 550 requests | exact rows 0.312 → 0.875 |
| Accounts never captured individually had no evidence to cite | Whole-store snapshots (`snapshot_scope`, full customer exports) prove absence | case_01 / case_02 verified |
| 9 evaluation cases came out COMPLETE with **no steps** (a claim without proof) | Read PDFs and screenshots; map catalogue labels (e.g. statement `NST-2026-0718-1842` → `export_1842`) | 8 of 9 now have evidence-backed findings; case_07 fixed |
| OCR misreads e-mails (`areedt433` for `areed1433`), but a near-match can also be a *different real person* (`g.silva76` vs `g.silva76.jr`) | Repair only same-length, 1–2 OCR-style swaps (1/l/i/t, 0/o, 5/s …) to exactly one known address, never an address typed in structured evidence, and only when corroborated in the same document or by a catalogue link for the same record; otherwise "uncertain" and unused. Every decision logged to `ocr_repairs.csv` | no false merges; same answers under Tesseract 5.3 and 5.4 |
| A catalogue claimed `marketing_001` belonged to the subject | A screenshot captured before `audit_at` shows it bound to someone else, which vetoes the claim | case_63 not falsely INCOMPLETE |
| Intent rules matched templates but failed 11/31 paraphrases ("I no longer want to continue using… delete") | Clause-level matching, negation checked next to the verb (before it, or after for ja/ko/fr), single-field removals are not account deletion, Unicode/accent folding, 12 languages | 31/31 paraphrases; all 550 real decisions unchanged |
| Hard-coded test of which evaluation cases are non-deletion | Replaced with checks over all 550 requests (112 distinct sentences, all reviewed) | no labels in tests |
| A legal hold seen only in activity defaulted to USER_PROFILE and was verified **absent** (case_287) | Unseen records take their category from the full system map | legal hold retained; test asserts no retained record is ever deleted |
| Identity edge cases: look-alikes, recycled addresses, formatting | Exact-only matching after cleanup; a token held by two users is ambiguous; unknown or ambiguous e-mails never authorise deletion | C4, C5 |

Hypotheses tested and **rejected** with data (not used):

- Password-change timing as a linking signal: no relationship with retained records.
- Identity-change audit codes: the 8 vs 14 code split is unrelated to deletion outcome.
- Accounts deleted soon after verification being interrelated: no timestamps support it and the accounts
  share zero identifiers.
- Request order predicting activity order: on 175 confirmed matches, "earlier request → earlier anchor"
  holds 40 times vs 47 against (case, user and account numbers are equally uninformative).

## 6. Output contract and reproducibility checks

`python code/evaluation/validate_output.py` checks every row of `output.csv` against the output contract:

- **File:** exact header; one row per request, no duplicates, sorted by `case_id`; valid JSON.
- **Status:** only the three allowed statuses. `NOT_APPLICABLE` has `[]`. `COMPLETE` has only
  VERIFICATION steps, each citing evidence. `INCOMPLETE` has at least one finding.
- **Steps:** exactly the 7 fields, `step_no` 1..n, phases never go backwards, and every
  operation/state pair is from the allowed tables.
- **Evidence ids:**
  - Findings cite evidence; remediation and future verification steps use `""`.
  - Every cited id exists (a file, activity or audit id) and was captured at or before that case's
    `audit_at`.
- **Remediation chain:** every finding has its remediation, and every remediation has its matching
  verification.

| File | Rows | Contract violations |
|---|---|---|
| `output.csv` (518 evaluation requests) | 518 | **0** |
| `sample_predictions.csv` | 32 | **0** |
| `dataset/sample_output.csv` (official answers, to check the validator itself) | 32 | 0 |

The validator itself was tested by breaking the output on purpose: dropping a row, unsorting, invalid
JSON, a finding without evidence, evidence on a remediation, a wrong state, broken numbering, reversed
phases, a finding in a COMPLETE row, evidence captured after `audit_at`, an unknown evidence id, and a
missing verification. All 12 were caught.

Reproducibility:

- `code.zip` was unpacked into a fresh copy of the repository and run on **Python 3.11 and 3.12** in an
  empty environment: no Tesseract, no pypdf, no network, no API keys.
- `output.csv` was **byte-for-byte identical**, with the same metrics and 0 contract violations.
- **Without scipy** the matcher falls back to greedy assignment (with a warning) and still scores
  status 1.000 and exact rows 0.906 on the samples.
- The unit suite (`python -m pytest code/tests -q`, 59 tests) covers identity, every evidence parser,
  intent on all 550 requests, subject safeguards, OCR repair and veto, and the retained-record safety
  property.

## 7. Known limitations

- **Tied anchors (10 pairs, 20 cases, flagged `AMBIGUOUS_ANCHOR` in `subject_checks.csv`).** Two
  identifier-free accounts processed for two subjects with identical status, report and audit times score
  exactly the same either way round; no participant data separates them, so one assignment is chosen
  deterministically and the ambiguity is reported instead of hidden.
- **No identity-verification data** exists, so forgery cannot be detected beyond the request text;
  the agent never invents a NOT_APPLICABLE.
- OCR output depends on the Tesseract version; the extracted text is cached in
  `code/cache/document_text.json` so every run of this submission sees the same text.

Diagnostics written on every run: `code/evaluation/subject_checks.csv` (language, identity match,
intent reason, flags: HISTORICAL_EMAIL 103, LOOKALIKE_IGNORED, REPEAT_REQUEST, AMBIGUOUS_ANCHOR,
NO_EVIDENCE_FOUND) and `code/evaluation/ocr_repairs.csv`.

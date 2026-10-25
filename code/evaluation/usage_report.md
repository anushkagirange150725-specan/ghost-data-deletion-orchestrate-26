# Token Usage and Cost Report

## Final full-dataset run (the run that produced `output.csv`)

Command: `python code/main.py`

| Provider | Model | Model calls | Input tokens | Output tokens | Total tokens | Avg tokens / request | Est. cost (USD) | Cost / request (USD) |
|---|---|---|---|---|---|---|---|---|
| — (deterministic pipeline) | none | 0 | 0 | 0 | 0 | 0 | 0.00 | 0.00 |
| **Overall** | | **0** | **0** | **0** | **0** | **0** | **0.00** | **0.00** |

518 requests (plus the 32 samples, which are processed together for global activity matching) run in
a few seconds of CPU. The first run also extracts text from 15 artefacts (4 PDFs with `pypdf`, 11
screenshots with local Tesseract OCR). That text is cached in `code/cache/document_text.json`; neither
tool is a hosted model and neither uses tokens.

## Why no model calls

Every decision in this task is exact-match logic over structured data:

- resolving current and historical identifiers;
- reconstructing each record's state at `audit_at`;
- applying `deletion_rules.csv`;
- ordering the steps;
- citing evidence ids.

Running this deterministically gives reproducible results, exact identifiers and zero cost.

The one language task, deciding whether `request_text` authorises deletion, is handled by a
multilingual clause-level rule layer (12 languages). It is checked on all 550 requests (540 deletion,
10 not; 32/32 samples correct; all 112 distinct sentences reviewed) and on 31 paraphrase tests.

## Development assistance (not part of the pipeline)

The code was written with help from an AI assistant (Claude, model `claude-opus-5-5`, in the claude.ai
app); every turn is recorded in `log.txt`. That assistance is not called by the submitted program and does
not affect the run above.

No API keys, credentials or secrets are used, stored or required.

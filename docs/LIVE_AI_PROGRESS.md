# Live AI Development Progress

Updated: 2026-10-31

This record describes the current working tree. No live model API was called during this work.

## Completed in this pass

- Review analysis now keeps rule-based classification as a separate explicit choice. If real AI is selected and the provider is unavailable or fails, the page shows the failure and does not create a rule-based substitute.
- Added a project-scoped document AI page that accepts a user-provided text snapshot and invokes the existing provider only after an explicit button click. The existing A3 schema and Evidence quotation checks remain in use. Successful same-input results are cached in the Streamlit session to avoid a second charge.
- Added real localized product copy to the existing localization page. It calls the existing localization AI service, requires owner permission and a human fact confirmation, limits source selection to Evidence in the current project, validates cited Evidence IDs and the requested output language, and keeps generated versions pending review.
- Added Simplified Chinese as a requested output language alongside English and German. Market selection remains US or DE, so language and destination market are separate.
- Added reminders that requests may incur charges and a timeout does not prove that the provider did not receive the request.
- Updated offline tests for the new no-fallback contract and added the AI document page to the seeded all-pages smoke test.

## Known boundaries

- The document AI page currently accepts parsed text pasted by the user. It does not read stored project files or provide PDF/DOCX/XLSX parsing. Its evidence identifiers are explicitly temporary snapshot identifiers, not persisted Evidence records.
- The product copy workflow uses existing project Evidence and validates schema, language, and cited Evidence IDs. It does not yet prove semantic support for every sentence, render the deterministic product specification table into the generated result, or provide a complete independent factuality report. The page discloses this limitation and keeps output unpublished.
- The review classifier calculates sample counts and shares in program logic and attaches source review excerpts. Root-cause statements remain model hypotheses and require review.
- A timeout may leave provider-side request state unknown. The app does not automatically retry. The operator should check provider usage before manually retrying.
- No true API request was sent. `scripts/check_model_api.py` was run in offline mode only; it reported the local provider configuration as present and `live_verified=false`.

## Verification in this pass

- `pytest tests/test_review_ai_ui.py tests/test_document_ai_service.py tests/test_localization_ai_service.py tests/test_localization_workflow.py tests/test_seeded_pages_smoke.py -q`: 45 passed.
- Ruff on changed Python files: passed.
- Python byte compilation for changed Python files: passed.
- `git diff --check`: passed; Git only emitted existing LF-to-CRLF notices.
- Full suite: `pytest -q` returned 258 passed. Full repository Ruff passed. Release verification passes all functional checks; its only failure is the expected dirty working tree because this turn does not perform Git writes.

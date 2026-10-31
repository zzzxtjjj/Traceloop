# A3 AI Document Understanding and Requirement Extraction

Status: Party A Python module implemented; Party B B5 persistence/authorization mapping remains to be integrated and jointly tested.

Current code is in the local working tree on `feature/zhang-ai-20261031`; the A3 changes are
not committed or pushed by this implementation task.

## Module

- Schemas: `services/document_ai_schemas.py`
- Service: `services/document_ai_service.py`
- Prompts: `prompts/document_analyze_v1.txt`, `prompts/requirement_extract_v1.txt`
- Tests: `tests/test_document_ai_service.py`
- Shared structured execution: `services/ai_service.py`

The module consumes an already authorized `DocumentSnapshot`. It has no database reads,
business writes, task creation, upload handling or permission resolver. B5 must authenticate
the actor, resolve project/file access, parse the file, and construct the snapshot from
Evidence records that belong to the current file version.

## Call Example

```python
from services.document_ai_service import analyze_document, extract_requirements
from services.document_ai_schemas import DocumentSnapshot

snapshot = DocumentSnapshot(
    project_id=project_id,
    file_id=file_id,
    file_version=file_version,
    filename=filename,
    file_type=file_type,
    parser_status="parsed",
    segments=authorized_text_and_table_segments,
    project_context=authorized_project_context,
)

analysis = analyze_document(snapshot)  # Uses configured OpenAI-compatible provider.
requirements = extract_requirements(snapshot, analysis=analysis.result)
# B5 persists the needs-review responses through its existing approval pipeline.
```

For isolated testing, pass a provider implementing `generate(*, prompt, schema,
repair_from=None)`. Tests use Mock providers. Calls go through `run_structured_model` with
`record_run=False`: Pydantic validation and bounded retry behavior are shared, while this
AI module does not write AiRun or any other database row. B5 must persist run metadata under
its single AiRun owner if its current lifecycle requires it.

## Inputs and Evidence

Each `DocumentSegment` contains a Party B Evidence ID, file ID/version, source locator,
segment kind (`text` or `table`), content and optional segment hash. `DocumentSnapshot`
rejects duplicate Evidence IDs and any segment whose file ID/version differs from the
snapshot. Project and file authorization must happen before constructing this DTO; a
caller-supplied ID alone is not proof of authorization.

The model returns only `{evidence_id, quote}`. Before returning either response, the service:

1. Rejects IDs outside the supplied Evidence set.
2. Requires each quote to be an exact contiguous substring of the corresponding segment.
3. Requires explicit/inferred facts, risks and requirement signals to carry citations.
4. Validates deadline source text against both the cited quote and original segment.
5. Copies file ID, file version and locator from the trusted input, never from model output.
6. Returns a SHA-256 hash of each cited excerpt, not a hash of the whole file.

An absence or uncertainty may be represented as `unknown`; it does not gain a fabricated
date, owner, page or source. Conflicts require at least two citations. Every response has
`status="needs_review"`, `review_required=true`, and `publishable=false`.

## B5 Mapping

| A3 response | B5 responsibility |
|---|---|
| `result.summary` | Save in DocumentAnalysis output/revision fields |
| `result.important_facts` | Map to existing fact-candidate fields, preserving `epistemic_status` |
| `result.requirement_signals` | Optional analysis-stage signals; not yet approved requirements |
| `result.conflicts`, `missing_information`, `risks` | Save as review material with source refs |
| `RequirementDraft` | Map to B5 `ExtractedRequirement` draft fields; preserve status and null values |
| `evidence_refs` | Resolve/validate against existing Evidence rows; persist actual foreign keys and source locators |
| `status`, `review_required`, `publishable` | Map to B5 pending-review state; do not publish or create Task |
| `model`, `prompt_version`, `input_hash` | Persist using B5's sole AiRun/request audit path |

The exact B5 Python names, field aliases, enum values and persistence function were not visible
in the available `D:\\hackson` checkout or remote-tracking branches at implementation time.
The response is therefore an Adapter-ready Python contract, not a claim of completed B5
integration. Preserve B5's existing database models and map at the service boundary.

## Errors and Boundaries

- Empty or unsupported parse output: reject before model invocation; B5 retains the original.
- Invalid model JSON: `ModelOutputValidationError` from the shared AI service.
- Timeout/provider failures: existing `TradeLoopError` subclasses propagate to B5.
- Invalid Evidence ID, quote, or deadline citation: `ModelOutputValidationError`; no response
  draft is returned.
- Input budget: uses the existing `validate_model_input_budget` character limit.
- Repeated calls: no caching or idempotency is implemented here; B5 owns request idempotency
  and should prevent repeated paid calls for the same request key.

## Local Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_document_ai_service.py tests/test_ai_service.py
.\.venv\Scripts\python.exe -m ruff check services/document_ai_schemas.py services/document_ai_service.py services/ai_service.py tests/test_document_ai_service.py
```

These checks use fake providers and do not call a real model.

Current verification: targeted tests `22 passed`; full project suite `256 passed`; full Ruff
check `All checks passed!`.

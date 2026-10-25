# TradeLoop V1 implementation status

Updated: 2026-10-25

## Completed and verified

| Area | Minimum implementation | Verification |
|---|---|---|
| Shared evidence foundation | BusinessObject, Evidence, Finding, links, dedupe and project ownership checks | Unit tests |
| Structured AI boundary | Pydantic validation, one repair retry, timeout/error state; invalid output is not persisted as business truth | Unit tests with fake provider |
| Supplier quotes | CSV validation, deterministic scoring, source evidence, clarification questions and human decision | Unit + workflow tests |
| Review evidence chain | Import metadata, record dedupe, rule classification, deterministic statistics, source excerpts and human review | Unit + workflow tests |
| Improvement tasks | Draft, publish, role state update, delivery Evidence, accept/reject gate | Unit + workflow tests |
| Daily review | Task-linked reports and deterministic blocked/overdue/missing-material reminders | Unit tests |
| Follow-up comparison | Count/share/sample-size comparison and non-causal limitation | Unit + workflow tests |
| Market rules | Platform, EU consumer-information and internal procurement rule types with source/version records | Unit tests |
| Access boundary | Project unlock UI and project ownership checks for evidence, reviews, quotes and tasks | Unit tests |

## Deliberate limitations

- No live model provider is configured. The review classifier is a transparent keyword-rule baseline; it is not
  labelled as AI. `services/ai_service.py` is the validated integration boundary for a future provider.
- The role selector is for hackathon demonstration. It constrains service operations but is not a real user identity,
  membership directory, session backend, passkey implementation or enterprise RBAC.
- SQLite `create_all` creates the new additive tables. There is no migration framework yet; V1 avoided changing
  columns in existing tables. Legacy quote rows receive explicitly marked backfilled Evidence when analyzed.
- Quote comparisons do not contain a product unit/specification, Incoterm, freight, duty, tax or full landed cost.
  The app asks for these values and does not invent them.
- Cross-file supplier/batch association is only created when the imported row provides the identifier. Similar names
  are not treated as proof of association.
- Rule coverage is intentionally small. `not_covered` means the source is missing/unverified or no usable rule is
  configured; a passed check is not a blanket compliance conclusion.
- Demo quote and review files are simulated. Any trend produced from them demonstrates workflow behavior only.

## Not implemented in V1

- Real model API calls and model-quality evaluation against a labelled review set.
- OAuth/SSO, real project membership management, server-side rate limiting and object-storage signed URLs.
- OCR/PDF/Excel review ingestion, semantic entity resolution and autonomous multi-agent execution.
- Automatic web monitoring for rule changes or legal advice.
- Database migrations, background jobs and production deployment hardening.

## Test scope

The automated suite covers missing/conflicting quote fields, duplicate reviews, invalid model output, packaging damage
without batch data, unproven supplier association, insufficient evidence, task completion without accepted evidence,
different sample sizes, invalid rule sources, unauthorized cross-project access, and two end-to-end workflows.

# TradeLoop V1 implementation status

Updated: 2026-10-29

Working branch: `integration/parallel-progress-20261029`

## Current verification baseline

- `python -m pytest -q`: **158 tests passed**.
- `python -m ruff check core services pages scripts tests`: **passed**.
- GitHub Actions workflow: `.github/workflows/ci.yml`, Python 3.12, pytest and Ruff.
- This branch is an integration branch. The final baseline becomes official only after both people review it and merge it into `main`.

## Completed and verified

| Area | Current minimum implementation | Verification |
|---|---|---|
| Shared evidence foundation | BusinessObject, Evidence, Finding, source locators, dedupe and project ownership checks | Unit tests |
| Structured model boundary | Pydantic validation, default one attempt; optional one repair only when `MODEL_MAX_ATTEMPTS=2`, plus timeout/error state and invalid-output rejection | Unit tests with fake providers |
| Model provider adapter | OpenAI-compatible request adapter, environment configuration, input budgets, default one-attempt policy and HTTP error mapping | Unit tests with fake HTTP responses; no live provider claim |
| Model readiness | Offline configuration check and opt-in single-request live check | Offline check currently reports unconfigured; live check has not run |
| Supplier quotes | CSV validation, mixed-currency rejection, deterministic scoring, source Evidence, clarification questions and human decision | Unit and workflow tests |
| Review evidence chain | Import metadata, review-ID dedupe, rule classification, deterministic statistics, source excerpts and human review | Unit and workflow tests |
| Cross-module traceability | Finding to source Evidence, task, delivery review, improvement record and follow-up batch; missing links remain explicit | Traceability workflow tests |
| Improvement tasks | Draft, publish, role-state transition, delivery Evidence, accept/reject gate and review notes | Unit and workflow tests |
| Daily review | Task-linked reports and deterministic blocked, overdue and missing-material reminders | Unit tests |
| Follow-up comparison | Count, share and sample-size comparison with a non-causal limitation | Unit and workflow tests |
| Localization versions | US and DE V1, feedback-based V2, parent link, persistence and rule results kept separate from generated content | Unit and page tests |
| Market rules | Platform, consumer-information and internal procurement rule types with source/version records | Unit tests |
| Membership access | Persistent User/ProjectMember records, member-scoped project lists, owner-only member addition, inactive-user/member rejection and access-code/member separation | Access-matrix tests |
| Access boundary | Project unlock UI and project ownership checks for evidence, reviews, quotes, tasks and traceability queries | Unit tests |
| Database migrations | Alembic baseline and non-destructive upgrade path for empty, legacy and repeatedly upgraded SQLite databases | Migration tests |
| Safe permission/error UI | Shared role-boundary notice and sanitised access, model, rule and validation error rendering across sensitive pages | UI tests |
| Demo delivery | Main-path and failure-case simulated CSV files, runbook, platform export note, third-party declaration, offline five-page pitch and 800mm × 1800mm SVG poster skeleton | File and content checks |

## Important capability boundaries

- The repository contains an OpenAI-compatible provider adapter, but the team has **not verified a real online model call** on this branch. A configured API key, an actual sandbox/live call and evidence-reference validation are still required before the team can say “real AI is working”.
- In this round's unconfigured environment, the offline check reports `configured=false`, `live_verified=false` and missing `MODEL_API_KEY,MODEL_NAME`, then exits with code `1`. This is the expected pre-configuration state, not an application fault.
- Input character/review budgets are enforced and `MODEL_MAX_ATTEMPTS` defaults to `1`. The project never runs `check_model_api.py --live` automatically; live verification requires explicit user permission.
- Local setup and safe-check instructions are in [MODEL_API_SETUP.md](MODEL_API_SETUP.md).
- When no model is configured, review analysis uses a transparent rule-based baseline. The UI must not label that result as AI.
- User and ProjectMember persistence, member-scoped project listing and owner-only member addition are implemented. A valid access code does not make a non-member a project member.
- The local user selector is an explicit hackathon identity context, not login authentication. Passing a user ID through service calls is not a production session or trusted identity boundary.
- The shared permission/error UI and project checks provide consistent, non-leaking feedback, but OAuth/SSO, server-side authentication sessions, passkeys and enterprise RBAC are not implemented.
- Alembic now provides a tested, non-destructive baseline and upgrade path for the supported SQLite states. This does not replace backups or prove compatibility with arbitrary production databases.
- The current local `data/tradeloop.db` is at revision `0002_project_membership`. Migration backups remain local and are excluded from Git; they are not release artifacts.
- Quote comparison does not calculate full landed cost and does not invent units, Incoterms, freight, duty or tax.
- Supplier, order and production-batch links are created only from supplied identifiers. Similar names are not treated as evidence.
- Rule coverage remains intentionally small. `not_covered` or “待确认” is not a compliance approval.
- Demo quote and review files are simulated. Any trend from them demonstrates workflow behavior only.
- The SVG poster contains a QR-code placeholder. The team must replace it with an approved final URL before submission.

## Not implemented or not yet verified

- Verified live model API calls and model-quality evaluation against a labelled review set.
- OAuth/SSO, production login/session identity, enterprise RBAC, production member lifecycle administration and production passkeys.
- Server-side rate limiting, object-storage signed URLs, background jobs and production deployment hardening.
- OCR/PDF/Excel review ingestion, semantic entity resolution and autonomous multi-agent execution.
- Automatic web monitoring for legal or platform-rule changes.
- Final organiser-approved poster export, final QR code, final submission channel and `hackathon-final` tag.

## Test scope

The 158-test baseline covers quote-field failures, mixed currency, duplicate reviews, structured-model failures, provider HTTP errors, model readiness and input budgets, model evidence-reference validation, packaging damage without batch data, unproven supplier association, cross-module traceability, missing evidence, task completion gates, different sample sizes, rule-source checks, localization version persistence, cross-project access, membership access matrices, Alembic migration safety, sanitised permission/error UI and two end-to-end workflows.

Tests prove deterministic code paths in the repository. They do not prove a real model provider, production identity system, production deployment or legal compliance.

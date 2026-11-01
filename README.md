# BL TradeLoop

BL TradeLoop is a Streamlit workspace for cross-border trade teams. It keeps project collaboration, source files, evidence, operational tasks, supplier information, customer feedback and AI-assisted document review within project-level permissions.

## Current Capabilities

- Email/password sign-in, server-side sessions, account verification flows, project membership and role checks.
- Project workspace, project chat and files, task assignments and delivery review, daily reports and project retrospectives.
- PDF, DOCX, XLSX, CSV and TXT parsing; PNG/JPG metadata and configured Tesseract OCR. HTML is not accepted as a business upload format.
- Document AI with dynamic attributes, strict schema validation, authorized Evidence checks and Chinese business-facing result views.
- Explainable file-routing recommendations. A project owner must review the recommendation before a draft task is created; drafts are not automatically published.
- Customer review import with flexible column mapping, duplicate detection and source traceability.
- Supplier quotation field mapping and deterministic price/currency/MOQ/lead-time checks. Incomplete public listings are not treated as formal quotations.
- DeepSeek-compatible model provider. Model output remains a draft and requires schema, evidence and human review.

## Project Layout

```text
app.py                  Streamlit application entry point
pages/                  User-facing workflow pages
core/                   Configuration, auth UI, models, schemas and shared UI
services/               Business logic and provider integrations
migrations/             Alembic database migrations
prompts/                Versioned AI prompts
scripts/                Migration, seed, backup, restore and health-check tools
tests/                  Service, security, parser and workflow tests
deploy/                 Ubuntu systemd, Nginx and logrotate examples
data/acceptance/        Local acceptance fixtures; excluded from this source-only push
```

## Local Setup

Use Python 3.11 or 3.12.

```powershell
cd D:\hackson
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts/migrate_db.py
streamlit run app.py --server.port 8503
```

Set `MODEL_API_KEY`, `MODEL_NAME` and `MODEL_BASE_URL` in the local `.env` or deployment secret store. Never commit actual credentials, local databases, backups or uploaded files. The application can run without a configured model; AI actions must report their actual readiness and outcome.

## Verification

```powershell
python -m pytest -q
python -m ruff check .
python -m compileall -q core services scripts pages app.py tests
```

The latest local regression run reported 342 passing tests. This does not mean every provider, OCR language pack, browser workflow or cloud deployment has been independently verified. See the workflow and deployment reports under `docs/` for the tested scope and remaining limitations.

## Data Included in This Push

This branch is source-only. It does not contain simulated acceptance fixtures, customer review datasets, Philips/ supplier source files, local live-AI responses or any other `data/` files. To run acceptance workflows, prepare authorized source data locally and keep its provenance/license alongside the files. In particular, public web availability does not by itself grant permission to redistribute a saved page or a compiled document.

## Deployment

Ubuntu 22.04 service examples are in `deploy/`; installation notes are in `docs/deployment/UBUNTU_22_04_DEPLOYMENT.md`. The examples must be reviewed for the target host before installation. No cloud server is configured by this repository push.

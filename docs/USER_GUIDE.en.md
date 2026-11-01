# Welcome to TradeLoop

Expand a section below. Return using **User guide** in the sidebar.

**Start here:** Projects → choose a demo user → load the demo project → enter `demo2026` → open Supplier quotes or Customer feedback. Use simulated data first.

**Review workflow:** Import reviews → analyze → check original text → confirm an issue → publish a task → submit evidence → obtain acceptance → compare later reviews.

## 1 · Projects

**Purpose:** Choose who is working and which project's records are used.

1. Select a local demo user; choose the owner for owner-only actions.
2. Load or select the demo project and unlock with `demo2026`.
3. Check user, project and role in the sidebar before continuing.
4. For your own work, create a user and project with product, markets and access code. The creator becomes owner.
5. The owner adds existing users as members with assigned roles.

**Check:** The correct project opens and actions match the role. Empty lists may indicate missing membership. Knowing the access code does not grant membership. Local user selection is a demo mechanism, not production login.

## 2 · Supplier quotes

**Prepare:** CSV using the page template or `data/demo/supplier_quotes.csv`; arbitrary Excel/PDF files are not supported here.

1. Upload, inspect validation and preview, then confirm import.
2. Select the batch in comparison. Review price, minimum quantity, lead time and payment terms.
3. Adjust weights and read ranking explanations.
4. Open source rows and clarification questions.
5. The owner selects a supplier and records a reason.

**Check:** Risks point to original fields. Ranking supports human decisions. Missing freight/tax terms prevent a full landed-cost claim. Fix missing columns or incompatible currencies; do not invent exchange rates. Duplicate files need not be reimported.

## 3 · Tasks & daily reports

**Prepare:** A published task. If none exists, confirm an issue and publish its task from Customer feedback.

1. The assigned role reads criteria and dependencies.
2. Update progress: `todo` = not started, `doing` = in progress, `blocked` = blocked.
3. Enter delivery details and verifiable supporting references.
4. Submit for review; submission does not complete the task.
5. The owner checks the material and accepts or returns it with comments. Role and review restrictions apply.

Link daily reports to tasks and record completed work, references, blockers and next steps. The progress review highlights overdue work or missing material. Reports do not replace delivery evidence. Missing reports do not prove poor performance.

**Check:** A task is complete only after acceptance. If a button is unavailable, check publication, role, evidence and reviewer eligibility.

## 4 · Customer feedback

**Prepare:** CSV. Practice using simulated `reviews_before.csv` and `reviews_after.csv` in `data/demo/`.

1. Upload, name and import a batch.
2. Select rule-based analysis or configured AI analysis.
3. Run once and wait. AI sends necessary review fields to the provider and may incur charges.
4. Open issues and inspect counts, original text and missing information.
5. Confirm, revise and confirm, or dismiss with a reason.
6. Draft a task and have the owner publish it; deliver and review it under Tasks.
7. Import later reviews, select baseline, follow-up and topic, then compare.

**Check:** Read counts, shares and sample sizes together. Review shares are not product failure rates. A decrease alone does not establish causation. Never assign supplier responsibility without reliable links. Duplicates are skipped; check whether an AI failure produced a rule-based fallback. Technical run details are optional.

## 5 · Content & checks

**Current page:** Manual V1, feedback and manual V2, plus independent rule checks. Real bilingual generation and two revisions are backend-tested but not yet connected here. There is currently no automatic V3 button.

1. Choose US English or German and save initial manual V1.
2. Select V1, enter feedback and revised content, then save manual V2.
3. Open history and compare differences. Existing V2 is not overwritten.
4. In rule checks, choose market and scenario, paste a title or contractual text and run checks.
5. Inspect risk, matched text, suggestion and rule source/version; revise and check again.

**Check:** Platform policy, consumer information and internal procurement standards are separate categories. No match is not full compliance. Missing coverage needs review. Interface language does not translate product copy; choose the target market separately.

## 6 · Settings

Supported business uploads: PDF, DOCX, XLSX, CSV, TXT, PNG and JPG/JPEG. HTML web snapshots are retained only as historical source material and are not accepted as business uploads.

Choose simplified Chinese, English or German. Untranslated hints fall back to Chinese; original evidence and saved records stay unchanged.

Keep local configuration if DeepSeek already works. To switch, select a provider, copy the account's API URL and model name, enter its own key and apply. Saving makes no request; the next analysis uses the settings. Test with a small non-sensitive batch. Only DeepSeek has been live-tested; other entries require verification.

Use the restore button to return to local `.env` configuration. Preferences are browser-session only and may disappear after the session ends. Do not share keys in chats or screenshots. On failure, check access, model, URL, balance and network.

# A6 AI 日报总结与项目复盘

`summarize_daily_report()` accepts a `DailyReviewSnapshot` assembled by the authorized B7
business layer. The snapshot contains the project, reporting period, submitted reports,
current task states, delivery submissions, program-computed overdue/blocked flags and
authorized Evidence. The service is persistence-neutral and uses the existing structured
provider with `record_run=False`.

```python
from services.daily_review_ai_service import summarize_daily_report
from services.daily_review_ai_schemas import DailyReviewSnapshot

snapshot = DailyReviewSnapshot.model_validate(authorized_b7_snapshot)
review = summarize_daily_report(snapshot)
```

The result is `DailyProjectReviewResult`. It separates employee claims from accepted
deliverables, repeats the B7 overdue and blocked flags without recalculating them, and returns
review-only coordination suggestions. It always has `review_required=true` and
`publishable=false`. It never approves a report, completes a task, changes an owner, creates a
Task or changes project progress.

For B7 integration, build the snapshot only after the current user passes project membership
checks. Map `DailyReport` to `DailyReportSnapshot`, task and `build_daily_risk_review()` output
to `TaskSnapshot`, task submissions to `SubmissionSnapshot`, and the existing source records to
`DailyEvidence`. Show the result to an authorized reviewer; do not pass it directly to task
publication or status transition functions.

The service rejects cross-project records, references outside the authorized Evidence set,
invented task risk flags, accepted deliverables without accepted submissions, mismatched quotes,
duplicate suggestion order, invalid JSON and timeouts. Missing reports and missing acceptance
records remain explicit missing information rather than being filled by the model.

# A5 AI 整改任务建议

`recommend_tasks()` consumes an authorized, already reviewed snapshot and returns
`TaskRecommendationOutput`. It is persistence-neutral: it uses the existing structured
model executor with `record_run=False`, creates no `Task`, and does not write an `AiRun`.

```python
from services.task_recommendation_ai_service import recommend_tasks
from services.task_recommendation_schemas import TaskRecommendationInput

request = TaskRecommendationInput.model_validate({
    "project_id": 7,
    "findings": [{
        "finding_id": 11, "project_id": 7,
        "statement": "评价中出现包装破损反馈。",
        "evidence_ids": [101], "review_status": "accepted",
    }],
    "evidence": [{
        "evidence_id": 101, "project_id": 7,
        "excerpt": "Review 11: package arrived damaged",
    }],
})
drafts = recommend_tasks(request)
```

The business layer should construct the snapshot only after checking the current member's
project access and review status. It may show the returned drafts to an authorized reviewer,
then map an approved draft into the existing B6 task creation request. `recommend_tasks()` must
not be called as a replacement for task approval or publication.

Evidence IDs and quotes are checked against the authorized input. Assignees are accepted only
when their IDs are in the supplied member list. A deadline requires an exact source phrase;
without one the model must return `null`. All outputs have `review_required=true` and
`publishable=false`.

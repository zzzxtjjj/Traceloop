# Prompt versioning

后续每个 AI 能力使用独立、带版本号的 Prompt 文件，例如：

- `supplier_summary_v1.txt`
- `task_plan_v1.txt`
- `daily_risk_v1.txt`
- `review_classify_v1.txt`
- `market_content_v1.txt`
- `semantic_validate_v1.txt`

Prompt 的输入和输出字段必须与 `core/schemas.py` 中的 Pydantic Schema 对应。


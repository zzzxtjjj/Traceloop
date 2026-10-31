# DeepSeek 接入步骤（简体中文）

核对日期：2026-10-31。

1. 打开 https://platform.deepseek.com/ ，注册并进入 API Keys，创建项目专用密钥，确认账户可用余额。
2. 在本机 `.env` 中填写以下配置，密钥不要发到聊天或提交 Git：

```dotenv
MODEL_API_KEY=在本机填写真实密钥
MODEL_NAME=deepseek-flash
MODEL_BASE_URL=https://api.deepseek.com
MODEL_TIMEOUT_SECONDS=60
MODEL_MAX_INPUT_CHARS=50000
MODEL_MAX_REVIEWS_PER_RUN=200
MODEL_MAX_ATTEMPTS=1
```

3. 使用项目独立环境做离线检查：

```powershell
cd D:\hackson
.\.venv-tradeloop\Scripts\python.exe scripts\check_model_api.py
```

4. 配置通过后，手动执行一次最小联网验证（会产生 API 请求和可能的费用）：

```powershell
.\.venv-tradeloop\Scripts\python.exe scripts\check_model_api.py --live
```

5. 预期显示 `live_verified=true` 和 `structured_schema_valid=true`。这仅证明最小请求连接与本地结构检查成功；评价分类还需在页面用少量样本检验证据引用、分类质量和人工审核。
6. 重启 Streamlit 后再在差评页面使用真实模型分析。先使用少量模拟评价，再使用有许可的真实公开评价。

官方当前推荐 `deepseek-flash`；旧名 `deepseek-v4-flash` 会转到当前 Flash 模型，不代表固定旧模型。项目对官方域名使用 JSON Object，关闭思考模式；Schema 放进提示词，本地仍执行 Pydantic 和证据引用校验。说明性输出要求简体中文，原文证据不翻译。

官方来源：
- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://api-docs.deepseek.com/guides/json_mode/

真实数据验证建议：Amazon Reviews 2023 用于评价分类和原文证据测试；Olist 用于订单、评价、卖家和配送记录的关系测试。先核对原始发布页许可，再下载小样本、保留原始 ID 和来源。两者不能直接称为“中国出海企业内部数据”，也不能替代真实采购报价或改进措施因果验证。没有生产批次和供应商资料的字段保持空缺。

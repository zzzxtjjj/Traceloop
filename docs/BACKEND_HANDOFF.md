# TradeLoop V1 后端接口与验收交接

> 2026-10-31 项目协作增量：参阅 [工作空间架构](PROJECT_WORKSPACE_ARCHITECTURE.md) 与 [甲方Prompt](PARTNER_A_EXECUTION_PROMPT.md)。下文已实现后端不包含尚未开发的持久化群聊、通用文件库、岗位需求提取和AI项目复盘。新增能力须逐步确认后实施；保留原有行业业务服务。

日期：2026-10-31。本轮不改页面。当前全量离线测试201项通过，Ruff通过。

## 1. 已有基础与本轮新增

报价、评价导入/去重/统计、问题审核、任务发布/交付验收、日报、复检和成员最小权限继续复用现有服务。

新增或补齐：

- 真实英德文案服务及两轮反馈追加：`services/localization_ai_service.py`。
- 版本列表、版本链、规则快照、差异和人工审核：`services/localization_workflow.py`。
- 每次生成自动对实际商品标题检查平台规则，不把包含元数据的JSON包当商品标题。
- 采购或消费者条款可独立检查，并与对应文案版本保存关联快照。
- 下一次修订传入上一版规则结果；每个新版本重新检查，审核状态从待确认开始。
- 规则核对日期超过180天或在未来时标记待确认。这是本项目复核策略，不是法规规定的期限，也没有自动联网更新规则。
- 公开Amazon JSONL小样本转换、去重、字段验证、来源清单和人工标注评估函数：`services/evaluation_data.py`。
- 本地数据转换入口：`scripts/prepare_public_reviews.py`，不请求模型、不下载数据。

## 2. 页面接入时使用的服务

这些是现有 Streamlit 技术栈中的 Python 服务函数，不是新建的公网 HTTP API。

### 生成初稿和继续修订

`generate_localized_copy(project_id, user_id, market, evidence_ids, facts_confirmed, parent_id=None, feedback="", provider=None, session=None)`

使用关键字参数。`market` 为 US/DE；`evidence_ids` 是当前项目中的来源；负责人确认后 `facts_confirmed=True`。初稿不传父版本；修订传最新父版本ID和反馈。只有项目owner可生成。

返回 Generation，包含 id/version/parent_id/feedback/market/language/prompt_version。`content` 是JSON包，字段为 platform、sources、ai_run_id、output。output包括title、bullets、description、missing_information、review_notes；每条文案含text和evidence_ids。

同一父版本已有后续版本时拒绝；新增事实请另起初稿。正文不变、标题超长、无效来源和坏结构不保存成功版本。不可仅根据引用ID合法认定语义完全正确。

### 列表与详情

`list_project_localizations(project_id, user_id, session=None)` 返回项目内模型版本摘要，包含id、market、language、version、parent_id、title。

`get_generation_chain(project_id, user_id, generation_id, session=None)` 返回从初稿到所选版本的历史，包含内容、反馈、父版本、checks、reviews、review_status及diff。查询者必须是项目成员。返回的是所选版本及祖先，不自动选择该版本之后的分支。

### 规则检查

`check_generation(project_id, user_id, generation_id, scenario="platform_product", text=None, rules_path=..., session=None)`

- platform_product：直接读取该版本实际标题。
- procurement：调用者提供真实采购条款文本，检查企业内部采购完整性，不作为法律结论。
- consumer_contract：调用者提供消费者条款文本；没有市场覆盖时明确返回待确认。

返回检查对象、文本、输入哈希、场景、规则结果和错误状态。快照作为AuditEvent关联Generation；各规则结果保留来源和版本。规则资料缺失不把文案生成伪装成失败，也不宣称检查通过。

### 人工审核

`review_generation(project_id, user_id, generation_id, decision, note, session=None)`

仅owner；decision为accepted/rejected，note必填。接受前重新检查规则，有失败、规则不可用或没有任何通过项则阻止。审核意见和内容哈希保存在AuditEvent。接受只代表人工文案审核，不代表对外自动发布、平台批准或全面合规。部分未覆盖项仍需人工理解并判断。

## 3. 真实数据验证入口

先从原始发布者取得许可明确的JSONL小样本，保留原文件，不覆盖模拟CSV。执行示例时将路径、来源和许可引用替换为真实值：

```powershell
cd D:\hackson
.\.venv-tradeloop\Scripts\python.exe scripts\prepare_public_reviews.py C:\你的目录\sample.jsonl --source-url https://原始发布者地址 --license-reference "许可名称和原始许可链接" --market US --batch "公开评价测试一" --limit 50
```

输出到 `data/evaluation/<输出哈希>/reviews.csv` 和manifest.json。目录不提交Git；已有目录不覆盖。评价ID稳定，去除来源用户ID和图片字段，不补造订单、供应商和生产批次。测试市场由操作者指定，不推断真实买家国家；来源商品ID也不等于企业内部SKU。

`classification_metrics(expected, predicted)` 接收相同评价ID集合的人工主题列表和预测主题列表，返回样本数、exact_match、micro precision/recall/F1和标签计数。ID缺失不静默忽略；分母为零时返回None。人工标签必须使用同一主题字典，星级不能直接当问题类别。

转换器不证明许可合法，不保证评价内容没有个人信息；模型调用前仍需复核评价正文。前N条抽样不是代表性随机样本，不能夸大结果。

## 4. 当前验证证据

- 离线201项测试、Ruff通过，包含已有迁移和页面回归测试。
- 上一轮真实DeepSeek已完成英语/德语V1→V2→V3复验；模拟资料，待人工语言与语义审核。
- 本轮新增规则整合和公开数据能力使用确定性测试，没有额外发起真实模型请求。
- 继续复验模型时，`scripts/verify_localization_live.py --live`会发送六次请求；不加--live不调用模型。它使用内存数据库和模拟事实，不能代替公开数据评估。
- 无新增数据库表或迁移；现有Generation/AiRun/RuleCheckRecord/AuditEvent复用。

## 5. 尚未完成的验收工作和边界

- 真实公开数据下载、许可复核、脱敏、人工标注及保留测试集的实测；不能把转换器测试说成真实数据评估通过。
- 文案语义依据、英语/德语自然表达及反馈质量的人工签字。
- 新生成/规则/审核服务接入操作页面；目前页面仍是人工V1/V2入口。
- 最终候选提交、两台电脑同步、新电脑复演和评审交付冻结。当前仍有未提交修改，不算干净发布候选。
- 本地身份选择仍非可信生产登录；并发版本唯一性没有数据库级锁或约束，服务层重复检查适合当前单机演示，不宣称生产并发保证。
- 未实现自动法律更新、全平台覆盖、生产队列和企业级安全系统。

后端核心链路已补强，但这些外部实测和集成条件仍必须完成后才能宣称整体交付验收通过。

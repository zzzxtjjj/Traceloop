# TradeLoop AI Backend契约 v0.2

日期：2026-10-31。状态：**方向与责任冻结，接口语义作为v0.2对齐基线；乙方物理字段映射待补充**。这不是已实现API或双方对未知字段的最终签署。

依据：[最终产品方向](TRADELOOP_FINAL_PRODUCT_DIRECTION.md)。原始[契约v0.1](audit/AI_BACKEND_API_CONTRACT.md)完整保留；本文件不覆盖审计或测试历史。

## 1. v0.1→v0.2变化

| 项目 | 动作 | v0.2约定 |
|---|---|---|
| 乙方开发状态 | 修改 | 已在开发；具体分支/代码不可见，不能当尚未开始；不要求停工或重写 |
| 入口优先级 | 修改 | 文件理解→需求→评价→批次总结→Finding→任务建议→日报→商品生成→商品验证；既有商品能力继续并行复用 |
| 身份/项目/输入授权、输出草稿、人工审核 | 保留 | 全部经过乙方业务后端；AI不改变正式业务状态 |
| 主键 | 保留并澄清 | 数据库实体int，SKU str；request_id可沿用乙方字符串；不要求UUID迁移 |
| Evidence DTO | 保留并补充 | 原文片段、类型、位置、版本、hash一并表达；来源标签≠数据库ID |
| AiRun所有权 | 修改：从待定变为明确 | 乙方唯一持久化；甲方执行与运行事件，复用现有AiRun，不再建另一套 |
| 已同步字段映射 | 新增 | 语义层冻结，物理名称保留乙方已有实现；缺字段先Adapter和能力声明，不改表凑文档 |
| 项目频道/文件上下文 | 新增 | 只提供授权引用；上传与消息不能直接触发隐式收费调用 |
| 语言 | 修改 | 商品目标locale支持zh-CN/en-US/de-DE；这是目标，不表示当前已验收中英德全部功能 |
| 所有九项一次实现、WebSocket、向量库、微服务拆分 | 暂缓 | 按M1～M5交付；不阻塞乙方已在做的基础设施 |

## 2. 公共DTO语义

下表字段名为对齐用规范名，不推翻已同步字段。如乙方已用user_id表示actor_id、file_id表示source_file_id，由边界Adapter映射，禁止双方各创建第二套业务实体。

### Request

| 规范字段 | 类型/约束 | 来源 |
|---|---|---|
| request_id | 非空有界str，跟踪一次调用 | 乙方生成/沿用已有ID |
| project_id | 正int | 乙方从授权项目确定 |
| actor_id | 正int，只来自认证主体 | 前端同名值不能作为可信身份 |
| task_type | 九种能力之一 | 服务端允许列表 |
| entity_type/entity_id | 允许类型+正int | 乙方目标实体，不能传任意表名 |
| input_refs | kind、entity_id、version的列表 | 乙方解析和鉴权，不让甲任意查库 |
| schema_version | str，例如1.0 | DTO结构版本，与文档v0.2不同 |
| idempotency_key | 非空有界str | 乙方统一管理并发和重放 |
| context | 按task_type区分的独立Schema | 授权快照，不能用一个任意dict直灌模型 |

商品请求context额外带product_id:int、variant_id:int、market:str、locale:str、fact_snapshot_version:str和template_version:str；platform可选。所有引用都必须属于project_id。商品/SKU身份未确定时不能凭名称猜测。

内部AuthorizedContext包含可信actor、权限、resolved_inputs、scope和snapshot_hash；不得由公开客户端自填。HTTP方案需要乙方服务鉴权；同进程方案注入可信上下文，不先改框架。

### Response

| 字段 | 约定 |
|---|---|
| request_id/status | status为succeeded/needs_review/blocked/failed；不是业务发布状态 |
| structured_result | 对应业务结果，失败时null；不塞入未经Schema校验的内容 |
| evidence_refs/findings/warnings | 授权引用、待审FindingDraft、可读限制；无正式Finding状态变更 |
| prompt_version/model/ai_run_id | 模型任务必保留；纯确定性验证可null，并保留请求审计 |
| input_snapshot_hash/content_hash | 绑定输入与输出；具体结果没有内容文本时输出hash仍绑定规范化JSON |
| review_required/publishable | AI建议需要审核；AI响应publishable固定false，不能由客户端改成true放行 |
| schema_version/error | 结果Schema版本；失败携带统一Error |

Error={error_code:str,error_message:str,retryable:bool,failed_stage:authorization/retrieval/input_validation/model_call/output_validation/fact_validation/persistence}。error_message不含密钥、Authorization头、业务原文或上游未脱敏响应。

实现时extra=forbid、长度/数量/哈希和枚举校验，并进行task_type/context/result一致性校验。这里是文档定义，Python类名和文件位置在接入时协商。

### EvidenceRef v0.2

```text
evidence_id: int（乙方真实主键）
source_kind: file | review | task_submission | daily_report | external_source
source_entity_id: int
source_version: str
file_id: int | null
file_version: str | null
locator: 按来源类型验证的结构
excerpt: str（授权、最小必要原文片段）
content_hash: str（该excerpt的SHA256）
```

- 文件来源必须提供file_id/version；评价/任务等来源不虚造文件字段。
- PDF页码、TXT行号从1开始；XLSX用sheet/cell_range；DOCX段落/表格；CSV评价以batch_id/review_id定位。格式实际未支持时返回INPUT_NOT_READY/UNSUPPORTED_FORMAT，不能伪造位置。
- 文件整体hash由乙方元数据持有，excerpt hash与整文件hash不要混用。修改原件或解析版本需生成新引用版本。
- AI输出必须在允许Evidence集合内，excerpt/span需与快照匹配；S05等外部标签另存source_label，不能填入evidence_id。
- 与现有Evidence.locator_json/excerpt/content_hash映射；file_version若现表没有，由乙方已有元数据或快照适配，不自动要求新表。

## 3. AiRun与业务写入冻结

| 对象 | 含义 | 唯一保存方 |
|---|---|---|
| AIRequest | 一次业务分析意图、授权、幂等/预算、输入版本 | 乙方请求存储，可复用既有机制 |
| AiRun | 一次实际模型执行的模型/Prompt/hash/时间/错误 | 乙方AiRun存储；甲方发运行事件 |
| Generation/业务草稿 | 版本化业务结果、审核意见、输出hash | 乙方业务服务 |

甲方仍维护run_structured_model的执行能力和事件字段。当前运行器直接写core.models.AiRun：短期通过乙方拥有的同一Session/Repository适配，不另插一份AiRun。待适配到位后再增量调整；不要求朋友重写已有存储。

当前review_ai_service会写Evidence/分类/待审Finding，localization_ai_service会保存Generation。联调必须明确调用**旧编排适配**还是**新纯分析入口**，不能两种保存流程同时执行。乙方拥有提交/回滚与正式状态；甲方不自行改乙方库。

失败运行不能随业务草稿事务回滚而丢失。乙方按现有事务实现选独立日志事务/可靠落档适配，甲方提供运行开始/成功/失败事件与尝试编号。当前尚未验证此失败持久化链，不能宣称完成。

## 4. 业务能力状态与Schema

以下“已有”指本机可见函数或验证原型，不代表v0.2标准端口已实现。全部业务正式状态由乙方控制，甲方只返回草稿。

| 顺序/接口 | 当前证据 | 请求context → 独立结果Schema | 阶段 |
|---|---|---|---|
| 1 analyze_document | 未发现完整实现 | file/extraction版本+文本表格块+Evidence → DocumentAnalysisResult（summary、fact_candidates、requirements、缺资料） | M1新增 |
| 2 extract_requirements | 未发现完整实现 | 解析/分析快照+岗位/候选成员 → RequirementExtractionResult（RequirementDraft列表） | M1新增 |
| 3 analyze_reviews | review_ai_service已有分类逻辑与写入耦合 | batch/review快照+taxonomy → ReviewAnalysisResult（分类、span、置信度、缺资料） | M2复用适配 |
| 4 summarize_review_batch | 程序统计存在，独立AI总结端口未发现 | 程序统计版本+样本量/分母/时间/基线 → ReviewBatchSummaryResult（解释、限制、Finding草稿） | M2新增 |
| 5 draft_finding | 现有评价逻辑产生待审Finding，非通用端口 | 事实/统计/证据快照 → FindingDraftResult（statement、认识状态、证据、替代解释） | M2复用/分离 |
| 6 recommend_tasks | 有规则任务创建原型，未见独立通用AI端口 | 已审核Finding/需求+岗位/授权成员/依赖 → TaskRecommendationResult（TaskDraft列表） | M3新增 |
| 7 summarize_daily_report | 有规则风险检测，无完整AI总结端口证据 | 真实日报+任务/验收快照+程序逾期 → DailyProjectReviewResult | M4新增 |
| 8 generate_product_content | 商品/原本地化两条原型均有；新链未接页面 | 商品scope+审核事实+类别/语言模板 → ProductContentDraft（marketing/spec/assembled/validation） | M5复用适配，甲可提前完善 |
| 9 validate_product_content | product_content_pipeline已有独立核验函数 | 内容hash+事实/模板/市场版本 → ProductValidationResult（checks、语言问题、人工项） | M5复用，默认不调用模型 |

原v0.1各业务Schema明细可复用；以下规则在v0.2保持：

- RequirementDraft：来源、原文、建议岗位/负责人、截止/依赖、交付物、验收标准、缺资料、待审。无法确定负责人/日期则null。
- ReviewAnalysisResult：每个输入review恰有一条分类，可多个主题；ID不重不漏；span是原文；统计由乙方程序计算。
- FindingDraft：观察事实/统计结果/原因假设分层；缺证据和替代解释显式返回，不自动追责。
- TaskDraft：来源、负责人建议、优先级、依赖、交付物、验收标准；正式负责人和任务ID由乙方决定。
- DailyProjectReviewResult：只引用真实任务/提交；文字已完成但未验收仍待验收，AI不批准日报。
- ProductContentDraft：已审核事实仍保留confirmed_as_listed性质，未知/冲突不补全；原始/最终分层；语言缺陷不因规格表完整而隐藏。

## 5. 错误、重试与过期

保留已有TradeLoopError.code（MODEL_TIMEOUT、MODEL_AUTH_ERROR、MODEL_RATE_LIMIT、MODEL_PROVIDER_ERROR、MODEL_BAD_RESPONSE、MODEL_BAD_JSON等），Adapter增加failed_stage，不改朋友已有响应格式时可加兼容外层。

| 情况 | 处理与状态 | 是否重新调用模型 |
|---|---|---|
| 无权项目/文件 | 调用前拒绝；不存在/无权引用使用一致外部策略 | 否 |
| 不支持格式/解析失败 | 明确错误，保留原件；INPUT_NOT_READY或DOCUMENT_PARSE_FAILED | 否 |
| 同key同payload/刷新/重复点击 | 返回已有或进行中状态；原子占用 | 否 |
| 同key不同payload | IDEMPOTENCY_CONFLICT；不覆盖结果 | 否 |
| 模型超时/断网 | 记录delivery_unknown，可能已计费；查询运行再由授权者决定新请求 | 不自动 |
| 401/无效JSON/事实不符 | failed或needs_review；留运行记录，不写正式状态 | 不自动 |
| 429/5xx | retryable可true，但不是无条件重发许可 | 受预算和投递状态约束 |
| 保存失败 | 重试同结果保存，不重新生成 | 否 |
| 文件/事实版本变化 | SOURCE_VERSION_STALE；旧结果保留但标过期 | 用户确认新的分析请求 |
| 审核后内容变化 | CONTENT_HASH_MISMATCH；重新核验和审核 | 核验默认无模型 |

幂等作用域：project+actor+task_type+key，payload_hash绑定输入版本和策略版本。成功、进行中、失败均要持久化；读缓存时也检查当前权限。一个业务请求可有多次**显式授权**模型尝试，每次有独立关联记录与预算；不得以“同一请求”名义偷偷进行格式修复收费。初期max_attempts=1。

“同key不重复收费”是系统内部不重复发起请求的验收目标；网络失败后供应商是否已计费无法单靠本系统保证，必须保留未知投递状态。不得承诺外部计费绝对为零。

## 6. 乙方现有实现兼容表

用户确认字段已同步，具体清单尚未提供。以下留空不猜测；后续只补表，不要求乙方改既有字段。

| 语义 | 本机字段/入口 | 乙方已有字段/入口 | 兼容动作 |
|---|---|---|---|
| 当前用户 | User.id；部分service收user_id | 待粘贴已同步字段 | 乙方身份转换actor，不信任前端role |
| 项目成员 | ProjectMember.project_id/user_id/role/status | 待补 | 映射权限与岗位，不按岗位推断授权 |
| 文件 | Artifact.id/stored_path/sha256/parse_status | 待补 | 保留朋友文件模型，输出授权引用 |
| 解析片段 | 未见通用DocumentExtraction | 待补 | Mapper转text/table/location，不重做解析 |
| 任务 | Task.owner_role/status/confirmed | 待补 | 保留朋友状态机，映射Draft/提交/验收语义 |
| 日报 | DailyReport.role/task_id/completed | 待补 | 绑定真实提交者和任务状态快照 |
| 商品/SKU | BusinessObject可用，无独立ProductVariant | 待补 | 映射scope，不新建重复商品表 |
| Evidence | Evidence.excerpt/locator_json/content_hash | 待补 | 外部来源标签与真实ID分离 |
| 运行/幂等 | AiRun已有，AIRequest端口未见 | 待补 | 乙方单写入所有权，复用现有表/服务 |

## 7. 首轮冻结与验收动作

- [ ] 双方把已同步字段清单贴入映射表，标类型/可空/枚举/版本；无需为此暂停各自开发。
- [ ] 公共Request/Response/Error/Evidence DTO语义确认；现有框架/字段名优先保留。
- [ ] 确认唯一AiRun持久化入口与幂等锁，不出现模型或业务双写。
- [ ] 用一份合成TXT/CSV解析快照联调文件→需求草稿→乙方保存；仅在乙方实际支持格式范围内宣称成功。
- [ ] 模拟越权/解析失败/无效JSON/保存失败/重复点击，模型计数与业务状态符合预期。
- [ ] 朋友新增功能按自身分支提交；联调时记录双方SHA和实际测试，不推测已合并。

本轮不实现以上端口、不调用真实API、不改原v0.1，也不要求朋友停止开发。

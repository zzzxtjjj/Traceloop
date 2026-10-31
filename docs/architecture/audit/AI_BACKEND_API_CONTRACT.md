# 甲乙 AI 后端接口契约 v0.1（提案，尚未实现）

本文件定义未来接口，不声明已有HTTP端点。先采用Python应用服务/依赖注入联调，若乙方选择HTTP，只为相同DTO增加传输适配，不另造业务逻辑。

当前已有接口不完全满足此契约：run_structured_model会保存AiRun；generate_localized_copy会保存Generation；analyze_review_batch_with_model会写Evidence、分类和待审Finding。它们需分离/适配，不得原样作为无副作用AI API暴露。

## 1. 调用与信任边界

```text
员工客户端 → 乙方身份认证/项目权限/幂等/授权资料快照
           → 甲方AI能力（Provider + Prompt + Schema + 事实校验）
           → 草稿 + Evidence引用 + AiRun
           → 乙方保存草稿 → 人工审核 → 乙方业务状态变更
```

- actor_id必须来自乙方认证会话，不能相信客户端JSON或角色下拉框。甲方只接受乙方签发/进程内可信的AuthorizedContext；HTTP方案须服务鉴权，并防止任意用户伪造上下文。
- project_id、entity_id、variant_id、Evidence ID全部服务端核对归属。授权在调用前、读取引用时、结果读取/持久化及最终发布时执行，不能只在首次请求校验。
- AI不接收或返回本机绝对路径、任意URL读取指令、上传内容中的权限指令。input_refs由乙方解析成授权片段；甲方不拿ID任意查全库。
- 身份与权限、存储、状态机、幂等锁由乙方负责。甲方负责预算检查、模型最小输入、结构化和业务事实验证，不以Prompt代替鉴权。
- 模型只返回草稿和建议。正式创建任务、发布Finding、确认事实、批准日报、发布商品文案均由乙方业务服务和人工审核完成。

## 2. 通用请求及响应

以下是**拟用Pydantic Schema定义**，只存于Markdown，不是新增Python源码。业务已有int主键，v0.1沿用int；外部SKU是str。示例类型别名和约束需实现时落实为验证器。

```python
class EvidenceRef(BaseModel):
    evidence_id: int
    source_version: str
    locator: dict  # 依source_kind校验，见下文
    excerpt_hash: str  # SHA256，小写64位hex

class InputRef(BaseModel):
    kind: Literal["file", "extraction", "review_batch", "finding",
                  "task", "daily_report", "fact_snapshot", "generation"]
    entity_id: int
    version: str

class EntityRef(BaseModel):
    entity_type: str  # 由task_type允许列表约束，不接受任意表名
    entity_id: int

class ProductScope(BaseModel):
    product_id: int
    variant_id: int
    market: str  # 乙方启用的market配置键
    locale: str  # 如de-DE，不能由market自动猜所有场景
    platform: str | None = None
    fact_snapshot_version: str

class AIRequest(BaseModel):
    request_id: UUID  # 单次跟踪ID，不能替代幂等键
    project_id: int
    actor_id: int  # 乙方从认证主体写入，外部同名值不采信
    entity: EntityRef
    task_type: Literal["analyze_document", "extract_requirements",
        "analyze_reviews", "summarize_review_batch", "draft_finding",
        "recommend_tasks", "summarize_daily_report",
        "generate_product_content", "validate_product_content"]
    input_refs: list[InputRef]
    schema_version: Literal["1.0"]
    idempotency_key: str
    context: TaskContext  # 按task_type分派的union，禁止任意dict灌入Prompt

class AIError(BaseModel):
    error_code: str
    error_message: str  # 用户可读，禁止原始上游响应/headers/key
    retryable: bool
    failed_stage: Literal["authorization", "retrieval", "input_validation",
        "model_call", "output_validation", "fact_validation", "persistence"]

class AIResponse(BaseModel):
    request_id: UUID
    status: Literal["succeeded", "needs_review", "failed", "blocked"]
    structured_result: TaskResult | None  # 与task_type匹配的union
    evidence_refs: list[EvidenceRef]
    findings: list[FindingDraft]
    warnings: list[str]
    prompt_version: str | None
    model: str | None
    ai_run_id: int | None
    schema_version: Literal["1.0"]
    input_snapshot_hash: str
    review_required: bool
    publishable: Literal[False]
    error: AIError | None
```

实现时所有对外DTO设extra=forbid；ID正整数，字符串长度、列表长度和hash格式有上限；task_type与context/result联合判别。错误结果structured_result=null，不把格式不合法的模型结果当正常草稿返回。needs_review不是业务审核通过，succeeded也仅表示分析成功；所有AI响应publishable固定false。

纯确定性validate_product_content可以没有模型和AiRun，此时model/prompt_version/ai_run_id为null，但必须有乙方请求审计。已进入模型执行即需AiRun，模型失败也必须保留运行状态。

### AuthorizedContext（乙方内部端口，非客户端输入）

```python
class AuthorizedContext(BaseModel):
    project_id: int
    actor_id: int
    permissions: set[str]
    resolved_inputs: list[ResolvedInput]
    scope: ProductScope | None
    snapshot_version: str
    snapshot_hash: str
```

ResolvedInput包含可信实体类型、版本、可用文本片段和EvidenceRef；既保留原始引用，也只把本任务需要的脱敏片段发给模型。姓名/电话/地址按需移除。AI请求里不携带密钥，结果和日志不记录密钥。

### Evidence定位

| source_kind | locator最小结构 |
|---|---|
| PDF | file_id、file_version、page（从1计）、可选bbox |
| DOCX | file_id、file_version、paragraph_index（从1计）或table/cell |
| XLSX | file_id、file_version、sheet、cell_range |
| CSV/评价 | batch_id、review_id或row_number；CSV行号约定含表头 |
| TXT | file_id、file_version、line_start/line_end（从1计） |
| 图片OCR | file_id、file_version、bbox、ocr_run_id；OCR不等于事实已确认 |
| 外部网页 | source_record_id、captured_version、section；URL是出处，不能由AI自动任意抓取 |

AI只能引用输入允许集合；输出span必须是对应片段的连续原文。允许多个Evidence支持一个草稿，但不能仅凭相似商品名认定同SKU。source label S05不能直接填入int evidence_id，测试适配器需显式映射。

## 3. 公共结果类型

```python
class FactCandidate(BaseModel):
    field_key: str
    value: str | int | Decimal | bool | None
    unit: str | None
    status: Literal["candidate", "unknown", "conflicting"]
    evidence_refs: list[EvidenceRef]
    missing_information: list[str]
    # candidate经乙方事实审核后才能变成confirmed/confirmed_as_listed

class RequirementDraft(BaseModel):
    draft_id: str  # 请求内临时ID，不是数据库主键
    extracted_text: str
    evidence_refs: list[EvidenceRef]
    suggested_role: str | None
    suggested_assignee_id: int | None
    confidence: float  # 0..1；不表示实际权限/能力
    deadline: str | None  # ISO8601含时区；不明确则null，不猜日期
    dependencies: list[str]  # 当前草稿ID或已授权任务引用，类型需实现时区分
    missing_information: list[str]
    review_required: Literal[True]

class FindingDraft(BaseModel):
    draft_id: str
    statement: str
    epistemic_status: Literal["observed_fact", "statistical_result", "hypothesis"]
    evidence_refs: list[EvidenceRef]
    missing_information: list[str]
    alternative_explanations: list[str]
    suggested_actions: list[str]
    review_required: Literal[True]

class TaskDraft(BaseModel):
    draft_id: str
    source_finding_ref: InputRef | None
    source_requirement_draft_id: str | None
    title: str
    description: str
    assigned_role: str | None
    suggested_assignee_id: int | None
    priority: Literal["low", "medium", "high"]
    deadline: str | None
    dependencies: list[str]
    deliverable: str
    acceptance_criteria: list[str]
    evidence_refs: list[EvidenceRef]
    missing_information: list[str]
    review_required: Literal[True]
```

以上精简Schema是待实现契约，不能与现有数据库模型字段逐一等同。正式ID、审核者、状态、created_at由乙方创建；AI不能伪造。缺证据的假设可以返回，但必须明确hypothesis和缺失信息，不能成为confirmed事实。

## 4. 九项能力接口

所有接口均由乙方先完成授权、引用解析和快照版本校验。下列“可重试”均服从第6节幂等策略，不代表允许自动重复收费。

### 4.1 analyze_document → DocumentAnalysisResult

- 输入context：source_file_id/version、乙方提供的DocumentExtraction文本块/表格、解析状态、可选ProductScope、提取目标。扫描件OCR未就绪则blocked，不谎称已读图片。
- 拟输出Schema：DocumentAnalysisResult {source_file_id:int, extraction_version:str, summary:str, fact_candidates:list[FactCandidate], requirement_candidates:list[RequirementDraft], evidence_refs:list[EvidenceRef], missing_information:list[str]}。
- 数据源：授权文件片段与定位，不是AI访问原始磁盘路径。
- 错误：DOCUMENT_PARSE_FAILED、INPUT_NOT_READY、INPUT_TOO_LARGE、MODEL_*、EVIDENCE_INVALID。
- 甲：理解文本/表格、提取候选、验证原文定位。乙：原件存储、基础PDF/DOCX/XLSX/CSV/TXT解析/OCR适配、DocumentExtraction持久化、文件权限与版本。
- 人工审核：候选事实/需求必须审核。允许受控重试；不自动写正式事实或需求表。

### 4.2 extract_requirements → RequirementExtractionResult

- 输入context：document_analysis_ref/version或同一提取快照、项目目标、允许岗位、经授权候选成员、已有需求去重键。
- 拟输出Schema：RequirementExtractionResult {requirements:list[RequirementDraft], missing_information:list[str]}。
- 数据源：已授权文本与岗位字典；建议成员必须属于提供集合，岗位名不代表能力或授权。
- 错误：SOURCE_VERSION_STALE、ROLE_UNKNOWN、EVIDENCE_INVALID、MODEL_*。
- 甲：岗位路由建议、依赖/交付条件解释。乙：ExtractedRequirement持久化、审核、选定负责人、转成业务任务。
- 人工审核：必须；可受控重试；不创建正式Task，也不通知员工。

### 4.3 analyze_reviews → ReviewAnalysisResult

- 输入context：batch_id/version、已去重的review_id/text/evidence_ref列表、taxonomy_version、允许主题。只发必要文本，不发无关个人信息。
- 拟输出Schema：ReviewAnalysisResult {taxonomy_version:str, classifications:list[ReviewClassificationDraft]}；ReviewClassificationDraft {review_id:str, themes:list[str], evidence_span:str, evidence_refs:list[EvidenceRef], confidence:float, missing_information:list[str], alternative_explanations:list[str]}。
- 数据源：乙方导入快照。每条评价恰好一项classification，可含多个主题；ID集合完整、不重复；span原文连续匹配；主题在允许集合。
- 错误：EMPTY_INPUT、REVIEW_ID_SET_MISMATCH、EVIDENCE_INVALID、TAXONOMY_MISMATCH、MODEL_*。
- 甲：分类和解释；复用现有_validate_output思路。乙：CSV验证/去重/批次、持久化分类与Evidence、任务权限；不复制第二套分类Prompt。
- 人工审核：分类可作待审分析，责任假设必须人工确认。可受控重试；禁止甲方直接写Finding业务状态。

### 4.4 summarize_review_batch → ReviewBatchSummaryResult

- 输入context：classification_snapshot_version、统计快照（样本量、主题count/share、分母、时间范围）、可选可比基线和改进实施日期。
- 拟输出Schema：ReviewBatchSummaryResult {summary:str, statistics_snapshot_ref:InputRef, finding_drafts:list[FindingDraft], limitations:list[str]}。
- 统计由乙方复用确定性统计服务计算；甲方验证count/share与快照一致，再让模型解释，不能让模型自己生成统计事实。
- 错误：STATISTICS_MISMATCH、INCOMPARABLE_BATCHES、INSUFFICIENT_SAMPLE、MODEL_*；样本不足通常needs_review+限制说明，非强行报系统失败。
- 甲：解释趋势、替代解释与限制。乙：统计、可比口径、批次版本与持久化。无销量时仅称评价占比，不称故障率；前后变化不证明因果。
- 人工审核：必须；可受控重试；不自动宣告改进有效或发布Finding。

### 4.5 draft_finding → FindingDraftResult

- 输入context：业务问题、事实/统计快照、允许Evidence、已有Finding版本、待确认关系。
- 拟输出Schema：FindingDraftResult {finding:FindingDraft}。
- 错误：EVIDENCE_INVALID、SOURCE_VERSION_STALE、UNSUPPORTED_ASSERTION、MODEL_*。
- 甲：区分观察、统计、原因假设，给缺失资料和替代解释。乙：Finding实体、审核、驳回、发布、历史和EvidenceLink。
- 人工审核：必须；可受控重试；不确定员工/供应商责任，不改变Finding状态。

### 4.6 recommend_tasks → TaskRecommendationResult

- 输入context：已审核Finding或需求快照、岗位/候选成员、授权任务依赖、项目截止规则、验收约束。
- 拟输出Schema：TaskRecommendationResult {tasks:list[TaskDraft], coordination_notes:list[str]}。
- 错误：FINDING_NOT_APPROVED、INVALID_DEPENDENCY、ASSIGNEE_NOT_ALLOWED、MODEL_*。未审核问题可用于预览，但不得返回“可发布”任务。
- 甲：描述、岗位/负责人建议、交付物和验收标准。乙：选定负责人、权限、冲突/环依赖复查、正式任务ID、通知、发布与验收。
- 人工审核：必须；可受控重试；不能创建、分配或发布正式任务。

### 4.7 summarize_daily_report → DailyProjectReviewResult

- 输入context：report_date/timezone、已提交DailyReport记录、任务/提交/验收快照、乙方计算的逾期列表和依赖状态。
- 拟输出Schema：DailyProjectReviewResult {summary:str, completed_task_refs:list[InputRef], pending_task_refs:list[InputRef], blockers:list[FindingDraft], coordination_suggestions:list[str], evidence_refs:list[EvidenceRef], missing_information:list[str]}。
- 数据源：真实提交，不根据员工文字把任务自动完成。完成列表必须来自任务已验收状态；未报告与未完成是不同概念。
- 错误：TASK_STATE_MISMATCH、SOURCE_VERSION_STALE、INPUT_NOT_READY、MODEL_*。
- 甲：复盘、偏差和协调建议。乙：日报收集/历史、任务状态、确定性逾期规则和保存/批准。
- 人工审核：必须；可受控重试；不能批准日报、验收任务或自动追责。

### 4.8 generate_product_content → ProductContentDraft

- 输入context：ProductScope、fact_snapshot、category_schema_version、template_version、目标平台/语言、允许功能与Evidence；可选明确的新反馈版本（本轮不实施反馈迭代）。
- 拟输出Schema：ProductContentDraft {scope:ProductScope, marketing_copy:str, claims:list[ProductClaim], specification_table:list[SpecificationRow], final_assembled_content:str, internal_warnings:list[str], unknown_fields:list[str], conflicts:list[FindingDraft], validation:ProductValidationResult, content_hash:str, review_required:Literal[True], publishable:Literal[False]}。
- ProductClaim须关联field_key、fact_id/version、Evidence和原文span；不能只报claims而不检查正文。SpecificationRow复用现有结构，补配置版本和scope。
- 甲：独立商品Prompt、renderer、核验和语言提示；输出raw/parsed/spec/assembled/validation分层证据。乙：事实快照授权、版本保存、Generation草稿与人工审批。
- 错误：SCOPE_MISMATCH、FACT_NOT_READY、REQUIRED_FIELD_MISSING、UNIT_INVALID、UNSUPPORTED_ASSERTION、MODEL_*。
- unknown必填、未确认冲突声明或语言缺陷需blocked/needs_review；允许受控重试，不自动发布。

### 4.9 validate_product_content → ProductValidationResult

- 输入context：现有内容版本/hash、ProductScope、对应事实/模板/规则快照；不能只传消费者任意assembled而无来源快照。
- 拟输出Schema：ProductValidationResult {checks:list[ValidationCheck], required_fields_present:int, required_fields_total:int, unsupported_claims_detected:list[str], language_issues:list[str], human_review_items:list[str], content_hash:str, fact_snapshot_version:str, template_version:str, review_required:bool, publishable:Literal[False]}。
- ValidationCheck {check_id:str, kind:Literal["fact","source","market","unit","completeness","language","platform_rule"], status:Literal["passed","failed","unknown"], field_key:str|None, evidence_refs:list[EvidenceRef], message:str}。
- 默认纯确定性、不调用模型；无法可靠判断的语义转人工。不为“验证接口”偷偷再计费；如未来增加语义模型验证，应作为独立显式任务和预算。
- 甲：事实/单位/规格/正文矛盾校验；乙：授权快照、审核版本、防止审核后篡改、发布门禁。
- 错误：CONTENT_HASH_MISMATCH、SOURCE_VERSION_STALE、TEMPLATE_UNKNOWN、EVIDENCE_INVALID。可无收费重复运行；不批准内容、不改正式状态。

## 5. 乙方需要提供的最小端口

以下是方法职责，**不是已经实现的HTTP路由**。HTTP路径留给乙方框架选择，不能双方各实现一套。

| 端口 | 必须行为 | 首次联调必要性 |
|---|---|---|
| authorize_ai_request(actor, project, task_type, refs) | 从真实会话鉴权，对象归属与权限校验；生成AuthorizedContext | 必须 |
| get_product_fact_snapshot(scope, version) | project/product/variant/market精确过滤；审核状态、属性类型、Evidence与版本 | 商品链路必须 |
| resolve_authorized_inputs(refs, actor) | 文件/评价/任务/日报片段；位置、版本、hash；不可返回任意全库资料 | 按业务逐项 |
| acquire_ai_request(key, payload_hash) | 原子幂等锁、状态、预算占用与重放 | 必须 |
| record_ai_run(run_event) | 接收甲方模型/Prompt/hash/错误/耗时；失败事务也留档 | 必须，先用单一适配器 |
| save_ai_draft(request_id, result, snapshot_hash) | 输出和Evidence复核后保存草稿；事务失败不改变正式实体状态 | 必须 |
| review_and_transition(entity, expected_version, decision, actor) | 人工审核+乐观锁+审计；分别实现Finding、Task、日报、文案状态机 | 按业务逐项 |

甲方提供九项能力的DTO/调用入口以及共享运行器；乙方调用它们，不再直接调用供应商生成第二份结果。甲方不能实现第二套User/Project/Task/File数据库。

## 6. 幂等、重试与预算

1. 幂等记录由乙方唯一管理，作用域为project_id+actor_id+task_type+idempotency_key；绑定规范化payload hash，包含引用版本、market/locale、schema与Prompt策略版本。
2. 同key同payload：返回同一进行中或已完成结果，不重新收费；读取结果仍执行当前权限检查。同key不同payload：IDEMPOTENCY_CONFLICT，不覆盖历史。
3. 并发相同请求先原子占用，只有一个执行者进入Provider。不能只用AiRun.input_hash或“已有Finding”查询当分布式幂等锁。
4. 模型调用后连接超时，供应商可能已处理，状态标unknown_delivery；不得自动解锁重发。操作者明确重跑才分配新key并消耗新预算。
5. 401/403、Schema错误、事实错误不自动重试。429/5xx/暂时网络错误可以标retryable，但由乙方调度器结合预算、供应商完成状态和人工选择决定是否重试。
6. 通用运行器现有max_attempts=2表示一次额外格式修复调用，会计费。正式接入初期明确max_attempts=1；额外修复必须显式授权并计入预算。
7. input_chars、review_count、超时、Token输出上限由甲方检查；乙方负责每项目/用户调用配额、重复点击禁用和任务并发限制。
8. 确定性检查可重复执行，模型生成不能因页面刷新再次运行。历史Round2的六次限额已经用完，本契约不新增任何真实调用授权。

## 7. 错误码与已有错误映射

| 错误组 | 规范码示例 | 默认可重试 | 备注 |
|---|---|---|---|
| 权限 | ACCESS_DENIED、REFERENCE_NOT_ACCESSIBLE | 否 | 对不存在/无权对象采用一致对外策略，避免泄露其它项目存在性 |
| 输入/解析 | INPUT_INVALID、INPUT_TOO_LARGE、DOCUMENT_PARSE_FAILED、INPUT_NOT_READY | 否 | 修正资料后新请求；保留原件 |
| 作用域/事实 | SCOPE_MISMATCH、FACT_NOT_READY、EVIDENCE_INVALID、UNIT_INVALID、REQUIRED_FIELD_MISSING | 否 | 不自动补全未知或冲突 |
| 版本/幂等 | SOURCE_VERSION_STALE、CONTENT_HASH_MISMATCH、IDEMPOTENCY_CONFLICT | 否 | 返回当前请求可知版本提示，不泄露对象 |
| 模型配置/鉴权 | MODEL_NOT_CONFIGURED、MODEL_AUTH_ERROR | 否 | 沿用core/errors.py，不返回密钥或上游原文 |
| 网络/供应商 | MODEL_TIMEOUT、MODEL_RATE_LIMIT、MODEL_PROVIDER_ERROR | 有条件 | retryable不等于允许立即重发 |
| 输出 | MODEL_BAD_RESPONSE、MODEL_BAD_JSON、UNSUPPORTED_ASSERTION、STATISTICS_MISMATCH | 否 | 无效输出不能写关键状态 |
| 持久化 | DRAFT_SAVE_FAILED、RUN_LOG_FAILED | 有条件 | 先保留结果，不重新调用模型；乙方只重试保存 |

HTTP适配建议：输入422、幂等/过期409、访问403或统一404、未配置503、上游502/超时504；框架未选定前不把HTTP状态当已实现。保留已有TradeLoopError.code，统一响应增加failed_stage，不把所有异常都叫“AI失败”。

## 8. 审核与版本门禁

- 草稿→待审核→已接受/驳回→正式发布由乙方控制；任务提交≠任务验收。
- 人工审核记录绑定actor、权限、content_hash、事实/模板/规则版本、意见和时间。内容或证据变化必须重新核验/审核。
- schema_version对结构破坏升级主版本；新增可选字段升级次版本；Prompt版本、taxonomy版本和市场规则版本独立。
- 输出保持raw_model_output、parsed、specification、assembled、validation独立且不可覆盖；日志脱敏，原始业务资料的访问遵守项目权限。
- 敏感操作不得由AI输出中的角色、review_required=false或publishable=true放行；服务端响应Schema禁止此种发布捷径。

## 9. 首个接口验收（待双方实现）

- [ ] 乙方用内存Stub返回两个SKU的授权事实快照，甲方生成请求不跨SKU。
- [ ] 甲方只返回草稿，乙方能保存并查询；没有自动业务状态变更。
- [ ] 未授权引用在模型调用前拒绝，Provider调用计数为0。
- [ ] 同幂等key并发仅一次模型调用；不同payload报冲突。
- [ ] 模型无效JSON、超时、未知参数、冲突、语言缺陷均有明确结果和运行记录。
- [ ] 内容哈希变更后，原人工审核不可用于发布新内容。
- [ ] 失败只重试保存时，不重复调用模型。

本轮不实现任何接口或迁移。乙方可依v0.1搭建端口、Stub和状态机，正式接入前须共同确认主键、身份、AiRun事务与版本策略。

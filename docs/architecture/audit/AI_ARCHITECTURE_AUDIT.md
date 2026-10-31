# TradeLoop 第一轮甲方 AI 架构审计

日期：2026-10-31。方法：读取当前工作区源码、检索调用关系、检查历史产物；不导入应用、不运行真实模型、不连接业务数据库。本轮只新增四份审计文档。

## 1. 仓库与证据口径

- 仓库：D:/hackson；分支：integration/parallel-progress-20261029。
- HEAD：267f401ab7b16a0fa34781f3e9628b01f70b2866。
- 工作区已有大量已修改与未跟踪文件，包括商品流水线；因此本审计针对**当前磁盘工作区**，不是仅针对HEAD提交。
- `.env`未读取、未修改；没有输出真实密钥。没有切分支、stash、reset、commit或push。
- 受保护源码、测试、页面、Prompt与product_validation历史文件共336个，写文档前后SHA256复核全部一致。
- 本轮未执行pytest或Ruff。仅用标准库ast.parse读取13个相关Python文件，语法解析通过，未导入应用或执行业务；这不等同于测试通过。四份Markdown代码围栏闭合检查通过。历史242 passed、Round2六次真实请求、49/49覆盖仅为历史执行证据，不代表本轮重新运行。
- Round2现有记录为PARTIAL、人工签署pending、publishable=false。德语hours和小数问题仍存在。
- 乙方尚未开始本次约定的正式开发。存量原型中存在Project、User、Evidence、Finding、Task等类，并不等于乙方已交付完整业务后端。

以下行号均来自当前工作区。审计范围只检查AI代码及其直接调用边界；不对不存在的聊天、文件解析等功能作安全认证。

## 2. 当前代码结构与真实能力

| 层 | 当前文件与入口 | 能确认的能力 | 不能据此声称 |
|---|---|---|---|
| 模型传输 | services/model_provider.py:25、64、117 | 可注入HttpTransport；OpenAI兼容请求；DeepSeek JSON Object分支；HTTP错误转换、超时 | 所有供应商协议均兼容；已通过当前真实连接验证 |
| 通用执行 | services/ai_service.py:16、37 | Provider Protocol；Pydantic结构化验证；输入哈希、AiRun；1或2次格式尝试 | 通用鉴权、可靠幂等、独立持久化失败日志 |
| 输入预算 | services/model_readiness.py:97 | 字符数和评价数上限；调用方可传限制 | 所有调用路径都必定执行预算检查；Token计费控制 |
| 事实检索适配 | services/product_fact_repository.py:20、34 | 文件基线哈希检查；product_id+market精确过滤 | 生产事实库、语义RAG、文件抽取、SKU隔离 |
| 规格渲染 | services/specification_renderer.py:18、34、134 | DTO与Repository Protocol；US/DE模板；状态、来源、单位、必填字段、确定性表格 | 任意属性可配置、任意市场、多SKU生产接入 |
| 内容整合与核验 | services/product_content_pipeline.py:29、58、290 | 动态marketing与固定spec分开；逐字段与最终表格行检查；部分自然语言规则 | 完整语义证明、语言自然度自动验收、自动发布 |
| 存量本地化 | services/localization_ai_service.py:29、38 | 独立LocalizedCopy Schema；Evidence引用；版本反馈；Generation草稿保存 | 已使用新的规格流水线；Evidence自动具备商品/SKU/市场证明 |
| 存量评价AI | services/review_ai_service.py:84、98、119 | 最小评价上下文；分类ID集合与原文片段验证；程序统计；待审Finding写入 | 乙方评价模块正式完成；通用无副作用AI接口；真实责任归因 |
| 人工审核 | services/localization_workflow.py:198 | 原入口需owner、规则检查与审核意见，记录审核事件 | Round2产物已接入这个发布门禁 |

新规格流水线由scripts/verify_dreo_renderer_round2.py调用。检索调用关系未发现页面直接使用assemble_product_content；不能把脚本验证等同于线上页面能力。

## 3. 优先级风险

P0表示**接入生产业务或双方联调前的阻断项**，不表示本轮已经证明发生数据泄露。

| ID | 级别 | 发现与代码依据 | 影响与最小处理 |
|---|---|---|---|
| A01 | P0 | ProductFact仅product_id/market，无project_id/variant_id；Repository也仅双参数。specification_renderer.py:18、34；product_fact_repository.py:25 | 同商品不同SKU无法精确隔离。乙方提供授权后的project+product+variant+market快照，甲方校验返回范围；不能拿当前协议直接作多租户API。 |
| A02 | P0 | 生产服务中的核验器仍使用DR-HSH006、120/230、50/60、1000/1300、34dB；product_content_pipeline.py:174、203 | 换商品后可能误杀合法参数或漏报其它参数。拆为通用字段约束与DREO测试策略；不可全局禁止德国50Hz或230V。 |
| A03 | P0 | review_ai_service.py:119、239、261直接读写业务表，函数没有actor_id和成员检查；ai_service.py:37也不负责鉴权 | 它们是存量内部服务，不是可直接暴露的安全API。乙方授权上下文后调用甲方纯草稿接口；乙方事务保存、送审。不要据此认定现有完整应用必然已被绕过。 |
| A04 | P0 | validator只遍历模型自报claims；营销承诺筛查是有限正则。product_content_pipeline.py:137、185 | 漏报claims的功能声明可能漏检；“not only … CE-certified”会因not跳过，问句也整句跳过。需要逐句证据映射、局部否定范围和人工门禁；不可宣称零幻觉。 |
| A05 | P0 | assemble_product_content生成的publishable恒false，但DTO可变；review_generation是另一套链路。product_content_pipeline.py:41、290；localization_workflow.py:198 | false是默认标志，不是权限系统。乙方发布接口必须重查权限、内容哈希、事实版本、检查结果和人工审核；客户端不能传true放行。 |
| A06 | P1 | ai_service.py:37使用业务Session保存AiRun；core/db.py:24异常会回滚；review_ai_service失败向外抛出 | 在自管事务失败时AiRun可能随业务回滚，不能保证失败可追踪。甲乙约定独立运行日志事务/受控持久化端口；不要以现有模型类存在代替失败路径验收。 |
| A07 | P1 | schema固定US/DE、en-US/de-DE；specification_renderer.py:22、71、87、97；product_content_pipeline.py:24、31 | 扩市场要改多处Python。配置market、locale、category模板和字段定义，保留现有模板兼容。 |
| A08 | P1 | 属性value均为str；LABELS决定能渲染哪些字段。specification_renderer.py:18、161 | 壶容量之外的转速、容量篮尺寸等新字段可能静默不显示。引入typed AttributeDefinition与模板引用；不把暖风机字段设为全类必填。 |
| A09 | P1 | product_fact_repository.py:39、60、71固定商品、网页状态映射和核验日期；Evidence ID为空 | 合理作为基线适配器，不能冒充生产审核。来源S05不是业务Evidence主键；乙方需提供真实文件版本和页/行定位。 |
| A10 | P1 | model_provider.py:158附近DeepSeek分支给系统消息追加简体中文要求；业务Prompt要求英/德 | 通用传输层混入业务语言政策，可能与任务冲突。Provider只控制协议；每个业务Prompt显式传locale。这是风险依据，未证明它是历史hours错误的唯一原因。 |
| A11 | P1 | DE渲染器格式化小数与Stunden；marketing仅传原文，product_content_pipeline.py:290 | 固定表格正确不代表动态文案本地化正确。新增语言检查项和review_required；历史T3～T6已显示缺陷，不静默改写原始输出。 |
| A12 | P1 | product_content_pipeline.py:143接受confirmed_as_listed对应模型confirmed | 为历史兼容保留的弱化不应成为新请求默认规则。新契约必须保持声明性质，旧输出仅显式legacy adapter使用。 |
| A13 | P1 | evaluate_agent_output按T3/T4/T6判断、规范字符串匹配缺项；product_content_pipeline.py:229 | 测试编号泄入共享业务模块；词面缺失不等于语义遗漏。移到测试评估器；分别统计raw、pipeline、人工结论。 |
| A14 | P1 | generate_localized_copy只核对Evidence项目归属和excerpt；localization_ai_service.py:58 | 同项目不同SKU/市场Evidence仍需上游筛选；事实确认布尔值不等于逐项事实审核。 |
| A15 | P2 | 固定max_tokens、未导出usage/响应版本；model_provider.py:157；AiRun无usage字段core/models.py:180 | 后续可加统一token与成本记录，不阻断最小演示；本轮不迁移。 |

补充：validate_final_content允许传assembled字符串，主要数量检查作用于marketing.marketing_copy。若未来允许调用方提交任意assembled文本，必须验证它与对应营销原文、规格块和内容哈希完全一致；不能只检查已知表格行存在。当前assembler自身直接拼接，风险来自未来接口错误复用，而非已证实的外部入口。

## 4. 硬编码分类（避免误判）

| 位置 | 分类 | 结论 |
|---|---|---|
| services/specification_renderer.py:97 heater_us/de_v1 | 合理类别配置，但嵌在共享代码内 | 暖风机模板本身合理；移至版本化类别配置，不能当所有商品模板。generic模板仅名称+型号不是已完成通用品类。 |
| services/specification_renderer.py:71、87 | 共享代码中的固定字段和单位白名单 | 无品牌数值硬编码；动态属性扩展仍受限制。 |
| services/product_content_pipeline.py:174、203、229 | 共享业务服务里的样本专属策略 | 需要迁出：型号、特定参数、噪声、T编号。 |
| services/product_fact_repository.py:34 | 位于services的测试基线适配器 | 函数明确load_dreo_baseline，业务范围可解释；应隔离命名/目录，另加生产Repository，不将其当通用检索。 |
| services/product_factuality.py | Step2样本评估器 | 品牌/型号评估合理，但与生产模块存在import耦合，宜独立为evaluation包。 |
| prompts/dreo_step2_marketing_v2.txt:13及后续 | 测试专用Prompt | DREO、S05、T3～T6合理用于这次测试；不可作为通用生产Prompt。 |
| tests/fixtures/dreo_316_step2_cases.json、tests/test_product_factuality.py | 测试夹具 | DREO固定值必须保留用于回归，不是架构缺陷。 |
| tests/test_specification_renderer.py | 测试 | 包含另一商品kettle用例，证明基础可重用，不证明完整跨品类支持。 |
| scripts/verify_dreo_step2.py、verify_dreo_renderer_round2.py；docs/product_validation | Demo/验证与历史证据 | 样本专属正常；不得删改历史或接入常规用户生成入口。 |

## 5. 数据与Evidence审计结论

core/models.py目前无独立Product、ProductVariant或SKU类；Project.product_name（:20）不是商品主数据。BusinessObject（:208）与attributes_json可用于增量适配，但尚未定义商品/变体的约束。不要新建重复业务对象而不先与乙方确认映射。

Evidence（core/models.py:225）已有project_id、source_entity_type/id、locator_json、excerpt、content_hash、business_object_id，是可复用基础。现在ProductFact的source_ids是外部来源标签，evidence_ids是字符串列表且基线为空，二者没有自动完成数据库关联。必须分开source label、Evidence主键、原文件版本与页/表/行位置。

当前商品资料进入事实库的路径是人工核对Markdown+JSON fixture→load_dreo_baseline→DTO，不是已实现的“上传任意文件自动建立事实库”。精确过滤已有product+market，缺SKU与项目；目前没有必要引入向量数据库。语义检索只能在授权范围内补充候选资料，不能决定未知值或解决冲突。

Unknown/Conflicting在renderer被排除并记录内部项；动态营销仍需语义审核。conflicts为dict草稿且persisted=false，不代表Finding生命周期完成。

## 6. 公共AI设施与独立业务能力

| 业务 | 可复用公共设施 | 必须独立的甲方逻辑 | 乙方上下文与保存 |
|---|---|---|---|
| 项目文档理解 | Provider、AiRun、Schema、预算 | DocumentAnalysis Prompt、页/表文本引用校验 | 原件、基础解析、授权片段、解析版本 |
| 岗位需求 | 同上 | RequirementDraft、岗位字典、缺失信息 | 项目岗位、授权候选人、审核和任务转化 |
| 差评分析 | 同上，复用分类验证思路 | 分类Prompt与逐评价Schema | 导入、去重、批次、Evidence存储 |
| 批次总结 | 同上 | 对程序统计作解释，禁止生成统计事实 | 乙方计算并签名的统计口径、版本、样本量 |
| Finding草稿 | 同上 | 事实/假设/未知分层Schema | Finding状态、审核、证据关联 |
| Task建议 | 同上 | 交付物/验收标准/岗位建议Schema | 成员权限、负责人选择、依赖、发布 |
| 日报总结 | 同上 | 基于task snapshot的差异解释Prompt | 实际任务/提交/验收与日报历史；确定性逾期计算 |
| 商品生成/核验 | 同上+renderer | 商品Prompt、类别规则、语言检查 | 商品/SKU/事实快照、审核、发布 |

项目文件理解、岗位需求、通用AI任务建议、AI日报总结未确认有完整实现。存量build_daily_risk_review是规则逻辑，不能称为已完成模型复盘。批次统计、Finding、Task等存量原型仅为接口对齐参考，不审计为乙方成品。

## 7. 决策

**具备通用化基础，但目前不是完整通用商品引擎。** 保留Provider、结构化执行、Evidence基础、确定性renderer；最小改动为作用域补齐、属性/市场配置、样本策略隔离、纯草稿接口、审核门禁及语言检查。实现顺序见PRODUCT_GENERALIZATION_PLAN.md，双方接口见AI_BACKEND_API_CONTRACT.md。本轮止于设计。

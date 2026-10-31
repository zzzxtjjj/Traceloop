# TradeLoop：小家电出口项目工作空间与 AI 协作架构补充

日期：2026-10-31。状态：目标设计与待开发清单，非已实现声明。

本轮仅更新文档。本文补充原架构，不替换商品事实、报价、英德内容、客户评价与质量改进业务。与旧文档冲突时，本轮范围、协作目标和优先级以本文为准；实现事实仍以代码及实测为准。

## 1. 产品定位与当前活动步骤

TradeLoop 面向宁波中小型小家电出口企业，是项目驱动的多人业务协作、AI 产品信息管理与质量改进平台。

每个项目是独立工作空间，将人、讨论、文件、客户要求、商品规格、AI 分析、岗位任务、每日汇报和质量证据关联起来。首期一个项目一个主群聊，无部门私有子频道。

业务链路：

```text
项目成员上传资料并讨论
→ 保留原件、确定性解析、页码/工作表/行号证据
→ AI 理解与岗位需求草稿
→ 人工核对事实/要求及授权范围
→ AI 任务草稿 → 人工批准发布
→ 员工执行、每日汇报、交付证据 → 人工验收
→ 程序核对状态和期限 → AI 项目复盘（带引用）
→ 客户评价 → Evidence/Finding → 纠正任务 → 后续复检
```

经确认的商品事实另可生成 US 英语和 DE 德语内容，经两次反馈形成 V1→V2→V3，再进行规则检查和人工确认。文件要求、客户愿望、评价症状都不自动成为商品真实规格。

业务验收仍停留在 Step 1：选择一种商品、一个明确型号及地区版本，建立真实事实清单。电暖风机仅是候选。本轮不选择商品，不开始 Step 2，也不授权实现下述协作功能。

## 2. 实际代码盘点

| 模块 | 当前基础 | 仍需开发或验证 |
|---|---|---|
| 项目 | Project、User、ProjectMember、项目访问码和成员校验 | 统一工作空间入口、可信独立账号会话 |
| 岗位 | owner / procurement / operations / quality | 销售、生产、工程、物流等新增岗位与授权矩阵 |
| 群聊 | 未发现持久化消息模型/服务 | 消息写入、成员查询、附件、刷新保留、去重 |
| 文件 | Artifact 保存项目、路径、哈希、解析状态；报价/评价CSV原件落盘 | 通用上传/授权下载、版本、上传人、类型校验与多格式解析 |
| AI | AiRun、结构校验、DeepSeek适配；真实连接及模拟商品双语修订有历史实测 | 通用文档提取、岗位需求与任务草稿、项目复盘 |
| 任务 | Task、TaskSubmission、草稿/确认/交付验收和Evidence | 文档需求来源、多岗位人员建议、强类型依赖和幂等发布 |
| 汇报 | DailyReport关联任务、阻塞、证据、计划；确定性复盘 | 用户级DailyUpdate结构、所需支持与多任务状态核对 |
| 行业业务 | 商品事实/来源、报价、评价、质量闭环基础；模型文案服务 | 小家电型号和真实资料未确认；真实数据评估待做 |

历史测试数不代表新增功能已存在。最近历史本机基线为201项离线测试通过；本轮未运行测试、模型请求、迁移或seed。

## 3. 工作空间信息架构

每个Project包含以下区域，均以同一project_id为边界：

| 区域 | 职责 |
|---|---|
| Overview（项目概况） | 项目目标、商品/市场、待审核需求、任务与阻塞摘要 |
| Project Chat（项目群聊） | 一项目一主群、消息历史、回复与授权附件 |
| Files（项目文件） | 原件、版本、解析状态、来源与下载 |
| AI Assistant（项目助手） | 对当前项目授权资料进行理解、需求提取和任务建议 |
| Tasks（任务中心） | 草稿审核、指派、执行、交付和人工验收 |
| Daily Updates（每日汇报） | 用户进度、阻塞、支持需求和项目复盘 |
| Members & Permissions（成员与权限） | 独立身份、成员、岗位、授权范围和加入方式 |

“使用教学”仍是全局帮助入口。此处项目Overview指业务项目概况，不恢复已删除的全局营销总览。报价、本地化、差评和质量改进从工作空间进入，保留各自模块职责。

## 4. 身份、岗位和权限

优先复用User/ProjectMember。目标角色映射（待实现）：

| 业务岗位 | 建议稳定标识 | 与现有关系 |
|---|---|---|
| Project Manager | owner | 复用负责人 |
| Export / Sales | export_sales | 新增；operations保持旧数据兼容，不自动改写人员岗位 |
| Procurement | procurement | 复用采购 |
| Production | production | 新增 |
| Quality Control | quality | 复用品控 |
| Product / Engineering | engineering | 新增 |
| Logistics | logistics | 新增 |

岗位用于路由，不代表员工能力、资质或全部授权。建议负责人仅在当前项目已激活且岗位匹配的成员中选择；无合适人员时留空。

P0实现前明确最小可信身份机制：独立账号、密码安全哈希或其他合适认证、服务端会话、退出和身份绑定。不得接受请求中任意sender_id作为真实身份，不得把当前演示下拉框当作可信登录。无需建设企业SSO，但“两个账号”必须注明是测试身份还是已认证身份。

| 操作 | 权限目标 |
|---|---|
| 读消息、文件、任务、AI分析 | 当前项目激活成员，且满足对象授权范围 |
| 发消息、上传、提交日报 | 以当前可信用户为作者，不能冒用他人 |
| 管理成员/授权 | 项目负责人或明确授予该能力的管理员；普通成员拒绝 |
| 发布任务/验收 | 负责人或明确授权人员；默认不向普通成员授予 |
| 任务执行 | 受分配岗位/人员和状态约束；提交不等于验收 |
| AI读取 | 先校验操作者权限，再限定项目与对象；AI没有独立越权身份 |

邀请码或访问码只用于加入申请/辅助入口。加入批准及成员记录与访问校验独立。停用或撤销成员后，新请求立即拒绝；不信任页面隐藏、文件路径或可猜ID。

## 5. 持久化群聊（P0）

候选ChannelMessage字段：message_id、project_id、sender_id、message_type、content、created_at、updated_at、reply_to（可空）、attachment_references、client_request_id。

- 消息、发件人和附件查询均执行项目成员验证；sender_id由会话派生。
- reply_to只能引用同项目消息；附件只能引用当前项目有权访问的文件。
- 使用(project_id, sender_id, client_request_id)唯一性避免重试重复发消息；不同真实消息不得按相同文本误去重。
- 查询按created_at、message_id稳定分页，限制内容长度与单页数量。
- P0用手动刷新或轻量轮询，不要求WebSocket。刷新后历史保留。
- AI消息明确标记AI、AiRun和来源，不冒用员工身份。P0可暂不支持编辑/撤回；updated_at仍保留。

## 6. 文件库与存储（P0）

优先扩展Artifact承担ProjectFile职责，而非另建重复文件表。接口可以返回file_id，内部映射Artifact.id。

目标元数据：file_id、project_id、uploader_id、filename、file_type/MIME、storage_location、file_hash、upload_time、version、parent_file_id、parsing_status。旧记录新增非空字段必须先设计兼容回填，不虚构上传人；历史来源不明允许unknown。

- 原件沿用本地受控目录 `data/uploads/<project_id>/`；数据库只存元数据，不存普通二进制文件。
- 上传校验大小、扩展名与文件签名/MIME、压缩包展开上限、文件名路径穿越和恶意内容。
- 服务端生成存储名，不信任用户文件路径；下载通过file_id解析并先校验成员与对象权限，不暴露真实磁盘路径，不把上传目录直接设公开静态目录。
- 同项目相同哈希提示已存在；不能以全局哈希查询泄露其他项目是否有同一文件。
- 解析失败保留原件和错误状态；写盘与数据库失败需回滚元数据或清理本次临时文件，不能误删历史原件。
- 新版本保留旧文件，父子关系不能跨项目。P1提供完整版本管理。

优先文件类型与能力必须分开标记：

| 格式 | 上传/授权下载目标 | 解析目标 |
|---|---|---|
| PDF | P0保留原件 | P0文本型PDF页码；扫描件标需OCR，不假装已读 |
| DOCX | P0 | 段落/表格定位；没有可靠页码时不得捏造页码 |
| XLSX | P0 | 工作表、行列、单元格；不执行宏或公式代码 |
| CSV | P0 | 行列、编码与字段校验，复用已有导入 |
| TXT | P0 | 编码、行号/字符区间 |
| PNG/JPEG等图片 | P0保留原件 | OCR/视觉解析需单独验证，未支持时明确unsupported/needs_ocr |

支持上传不等于支持理解；每种解析器必须有正常、损坏、空文档和超限样例。依赖、解析库及授权由后续方案确认，本轮不安装。

## 7. 文档理解、需求提取与任务草稿（P0）

确定性解析先产生DocumentExtraction：文件ID、项目ID、解析器和版本、文件哈希、文本/表格片段、定位器、状态、错误与时间。与文件解析结果分离的模型分析使用已有AiRun。

再由AI生成ExtractedRequirement草稿：requirement_id、project_id、source_file_id、extraction_id、source_location、extracted_text、requirement_type、suggested_role、confidence、missing_information、review_status、model_run_id。

提取客户需求、商品规格声明、交付、采购和检测要求。每条都记录页码/工作表/行号或可验证片段；定位超界、原文不匹配或跨项目引用必须拒绝。confidence是模型判断，不是已校准概率或事实真实性证明。

文件指令为非可信数据；不执行嵌入命令、不启用宏、不让“忽略权限”等文字改变工具权限。规格声明先pending_review，资料冲突标conflicting，未知不补全；经过确认才能用于ProductSpecification或对外内容。

任务建议复用Task，目标字段：task_title、task_description、assigned_role、suggested_assignee、priority、deadline、dependencies、source_requirement_id、source_evidence、deliverable、acceptance_criteria。检查项目成员匹配、依赖循环、日期歧义及缺资料；建议负责人可为空。现有Task缺的字段再增量设计，不能让页面或AI直接写状态。

全部先draft。负责人/明确授权人员审核Accept/Modify/Reject；修改保留前后记录，发布独立人工确认。发布和从需求建草稿要有持久化幂等键/唯一约束。任务交付与验收复用现有Evidence/TaskSubmission。

## 8. 每日汇报与AI项目复盘（P1）

优先扩展DailyReport承担DailyUpdate职责，除非证明一条日报不能表达需求，不重复建语义相同表。新增author_id、report_date及必要列表字段，保留旧数据。

契约：completed_tasks、pending_tasks、blockers、required_support、next_steps、evidence_references。任务/证据必须同项目且操作者可访问；存用户陈述，程序核对实际任务状态。用户说已完成但未验收时显示“自报完成，待验收”，不改成done。

项目复盘按明确时区和时间窗运行：程序计算实际已验收、待办、逾期和依赖状态；AI总结当天实际提交的进展、跨岗位阻塞、资料缺口、风险和协调建议。输出每条关联task_id、daily_update_id、evidence_id或规则依据；未提交日报只说资料缺失，不编造进度或评价员工能力。

复盘复用AiRun并保存输入哈希、模型、Prompt、状态、耗时和结构验证。无足够输入明确证据不足。通知P1仅保留基础待办提醒；P2再做复杂通知。

## 9. 增量模型决策（均未实施）

| 实体 | 决策与原因 | 主外键/一致性与空值 | 旧库影响 |
|---|---|---|---|
| ChannelMessage | 新增，当前无消息持久化 | id主键；project/user外键；reply可空且同项目；附件ID需校验；幂等键唯一 | 新表，迁移验证 |
| ProjectFile | 优先扩展Artifact，不另建重复表 | 沿用id/project；uploader/parent关联；旧上传人未知可空；项目+哈希/版本约束需设计 | 增列与回填，不删除原件 |
| DocumentExtraction | 新增，区分原件与可复用解析结果 | id主键，project/file外键；解析器版本+哈希去重；错误可空，状态必填 | 新表，原件不受影响 |
| ExtractedRequirement | 新增，人工审核前的文档要求 | id主键；project/file/extraction/AiRun引用；建议岗位可空；审核记录保留 | 新表，复用Evidence定位 |
| DailyUpdate | 优先扩展DailyReport | 原id/project/task保留；新增作者和日期，旧作者未知可空；任务列表强校验 | 兼容旧日报 |
| Notification | P1按需要决定是否新增 | 若新增须project/recipient、来源对象、read_at可空及幂等约束 | P0不建 |
| ProjectChannel | P0不建 | project_id即唯一主群边界 | 无 |

User、ProjectMember、Task、Evidence、Finding、Generation、AiRun均不重复创建。MarketRule不是当前ORM表；目前规则来自JSON及RuleCheckRecord，不能因目标名称而再造一套。Product/SKU/ProductSpecification按行业步骤后续盘点，BOM/零件表仅有实际业务需要才增加。

## 10. 接口原则与甲乙契约

保持现有Python服务与Streamlit架构；无需为了群聊新建微服务。所有读写入口要求可信actor与project_id，后端先鉴权，再解析对象、分页、读文件或调用模型。参数中的actor不能冒充会话身份。

契约先评审：list/send messages；list/upload/get/download files；parse file；extract/review requirements；draft/review/publish tasks；submit/list daily updates；generate/get project review；invite/manage members。

每个契约注明输入、返回Schema、权限、幂等键、状态、异常、是否调用模型和数据范围。AI响应坏结构/超时仅保存失败记录，不发布任务。多个关联对象逐项校验project_id，而非只检查最外层项目。

## 11. 优先级与进入条件

- P0：工作空间入口、独立身份和项目权限、持久群聊、文件上传/授权下载、文档解析、需求证据、任务草稿/人工发布。
- P1：用户每日汇报、AI项目复盘、文件完整版本管理、基础通知。
- P2：WebSocket、部门子频道、在线状态、复杂审批与通知。

实施顺序：身份/契约 → 消息 → 文件 → 解析 → 需求/任务 → 既有行业业务连接 → DailyUpdate/复盘。必须经过用户逐步确认，不因本文存在自动开始开发。若比赛期限不足，报告硬性验收缺口并简化实现，不把功能降级说成完成。

验收清单见WORKSPACE_TASK_CHECKLIST.md；甲乙执行Prompt分别为PARTNER_A_EXECUTION_PROMPT.md和PARTNER_B_EXECUTION_PROMPT.md。

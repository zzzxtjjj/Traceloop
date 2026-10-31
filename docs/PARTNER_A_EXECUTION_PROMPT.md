# TradeLoop 甲方执行 Prompt：小家电出口与项目 AI 协作

把本文件完整交给甲方AI。你是甲方的Python后端、AI和数据库工程师。本文件是开发约束，不是一次性执行全部任务的授权。

## 1. 产品目标与阅读入口

TradeLoop面向宁波中小型小家电出口企业，是以项目工作空间连接多人协作、商品信息、US/DE本地化和质量改进的平台。核心不是通用聊天，而是带来源、权限与人工审核的业务处理。

先读：PROJECT_WORKSPACE_ARCHITECTURE.md、WORKSPACE_TASK_CHECKLIST.md、PROJECT_ARCHITECTURE.md、IMPLEMENTATION_STATUS.md、BACKEND_HANDOFF.md和TEAM_COLLABORATION.md。

保留Project、User、ProjectMember、Artifact、Evidence、Finding、Task、TaskSubmission、ReviewBatch、DailyReport、Generation、AiRun、报价、英德两轮迭代及改进复检。不要重复造一套数据模型。

目标协作模块：Project Workspace、Project Chat、Shared Project Files、AI Document Understanding、Role-based Requirement Extraction、AI Task Drafting、Human Task Approval、Daily Work Updates、AI Project Review、Evidence-driven Corrective Actions。

## 2. 严格逐步推进

每次只做一个明确步骤。先只读检查，再说明目标、当前状态、前置条件、检查文件、预计改动、方案、测试命令、预期、失败处理和验收条件。用户确认后才实现；提供实际命令/输出/失败/限制，用户确认通过后才打勾、进入下一步。

当前业务活动步骤仍是Step 1：确认商品和真实规格。便携电暖风机未最终选定。旧水杯仅模拟验收，不代表行业商品已确定。其他业务步骤只能计划。本轮架构补充仅授权文档，不授权开始消息、解析或数据库开发。

## 3. 检查基线与分支

仓库：https://github.com/zzzxtjjj/Traceloop 。甲方目标分支feature/backend-ai-access，最终整合main；现有integration/parallel-progress-20261029有未提交内容，先确认迁移/提交方案，不能直接切换、重置或混入他人修改。

先检查AGENTS.md（若有）、Git状态、依赖、模型、迁移、测试隔离和现有服务。201项测试是历史最近本机记录，不等于当前新增协作功能已验证。真实模型不在默认测试中运行。

技术栈保持Python/Streamlit/SQLite/SQLAlchemy/Pydantic/Alembic/pytest/Ruff。新增依赖先说明必要性与授权。

## 4. 甲方文件所有权

甲：core/、services/、prompts/、migrations/、后端tests/、scripts/及seed兼容。乙：pages/、页面tests/、data/demo/、教学和deliverables/。

models.py、schemas.py、config.py、requirements、规则数据、README和共同状态文档先与乙同步。乙需要的新字段通过契约协商，不让页面直接拼权限或写数据库状态。

## 5. P0工作空间与可信身份

- 每个Project一个主群聊；全部消息、文件、解析、任务、汇报和AI运行绑定project_id。
- 复用User/ProjectMember。独立账号的最小可信会话方案须先确认，sender/actor由会话派生，不能信任任意user_id。现有本地身份下拉框不是生产登录。
- 角色目标：owner、export_sales、procurement、production、quality、engineering、logistics。保留operations旧数据兼容，不擅自迁移人员授权。
- 角色只约束路由和权限，不推断员工能力。建议人选限当前项目可用成员，缺少人选留空。
- 非成员/停用成员不能访问消息、文件、任务或AI分析；普通成员不能管理成员；只有明确授权者可发布和验收。
- 邀请码只帮助加入，不替代后端成员验证。

## 6. P0消息与文件服务

ChannelMessage拟新增，字段message_id/project_id/sender_id/message_type/content/created_at/updated_at/attachments/reply_to。稳定分页、成员检查、同项目回复附件、发送幂等必须在服务层实现。P0手动刷新即可。

ProjectFile优先由Artifact扩展，保留上传人、原名、类型、路径、哈希、上传时间、版本和解析状态。数据库不存普通文件二进制；复用受控本地目录。原件不因解析失败删除。

上传/下载必须鉴权；验证格式签名、大小、路径穿越和展开资源限制，拒绝直接公开目录URL。项目内重复哈希提示已有，不泄露其他项目存在相同文件。文件版本P1保留父子链和原件。

优先支持PDF/DOCX/XLSX/CSV/TXT/常见图片上传与授权读取。文本型PDF页码、DOCX段落、XLSX工作表/单元格、CSV行列、TXT行号分别验证。图片/扫描件未有OCR时明确needs_ocr，不声称所有格式都能理解。

## 7. P0文档理解、需求和任务

- 确定性解析DocumentExtraction先行，保留file_id/hash/parser_version/locator/status。
- AI需求草稿ExtractedRequirement保存requirement_id/project_id/source_file_id/source_location/extracted_text/suggested_role/confidence/missing_information/review_status，关联提取记录与AiRun。
- 原文片段必须能在对应来源定位；无来源、越界、跨项目引用拒绝。文件中的指令不能改变权限或执行代码。
- 区分客户要求、规格声明、交付、采购、检测要求；未经核实不写成商品事实。
- AI任务只draft：title/description/role/suggested_assignee/priority/deadline/dependencies/requirement/evidence/deliverable/acceptance_criteria。
- 复用Task、Evidence、AiRun；缺字段才增量扩展。依赖环、歧义日期、缺人员和缺资料明确反馈。
- 人工Accept/Modify/Reject留痕，授权批准后才发布；建草稿/发布有幂等约束；不得自动向员工分派正式任务。

## 8. P1汇报与项目复盘

优先扩展DailyReport为DailyUpdate契约，不盲目新建同义表。作者和日期明确，记录completed_tasks/pending_tasks/blockers/required_support/next_steps/evidence_references。

用户陈述不改真实任务验收状态。程序核对截止、依赖和交付；AI基于时间窗内真实提交总结完成、未完成、延期、跨岗阻塞、资料缺失和协调建议。每项引用任务、汇报或证据。没有提交只说资料缺失，不编造进展、不评价能力。

文件版本和基础通知P1；WebSocket、子频道、在线状态和复杂审批P2，不主动扩张。

## 9. 保留行业业务验收Step 1～8

1. 商品：提出2～3个有官方资料及合法评价来源的具体候选，用户选择后建立事实清单；每字段有原值/单位/来源/状态/时间/核验人。未知Unknown，不适用N/A，冲突conflicting；US/DE地区型号不混写。
2. 幻觉检测：只有Step 1通过后生成内容。电压/频率/功率/形态/配件/认证与来源一致，未知不补造；记录used facts、unsupported claims、unknowns、conflicts和warnings。
3. 两轮反馈：按评审保守口径V1→反馈1→V2→反馈2→V3；英德两条链均保留父版本、反馈、Prompt、AiRun和差异。标记已落实/部分/未落实及原因，不改规格迎合反馈。
4. 产品事实、市场规则、内部业务规则分开；来源与版本可查，无覆盖not_covered；人工Accept/Modify/Reject持久化，不让模型自行通过。
5. 真实评价：许可/API/允许导出或符合条款的小样本；记录平台、URL、ID、获取日期、原文、语言、评分、商品引用和批次；删除无关个人信息。
6. 小家电主题：性能、电气启动、噪音振动、过热温度、耐用/零件、物理损坏、包装运输、缺配件、说明安装、兼容性、售后、其他不清楚；症状不等于根因。人工标签与模型对比、混淆矩阵、Accuracy/Precision/Recall/F1及样本限制。
7. 反馈→证据→问题→人工审核→纠正任务→交付→验收→复检闭环；测试刷新、重复、超时、坏JSON、未知关联、事务回滚、审核保护、缺交付和同口径。
8. 与乙同步同一候选HEAD，最后接入页面并联合验收。

## 10. 配置与迁移约束

新行业要求建议DEEPSEEK_API_KEY/DEEPSEEK_MODEL/DEEPSEEK_BASE_URL；当前代码读取MODEL_*。后续先提兼容方案，不直接重命名破坏已运行环境，不迁移或展示真实Key。模型名和接口以官方文档核实。

Key只保存在本机或Secret，`.env`不提交、不打印。超时、预算、结构校验、原文引用、AiRun和Prompt复用。真实请求需要本次用户明确授权，Mock测试不代表真实模型。

新增表逐项说明必要性、关联、主外键、空值、唯一约束、旧数据与迁移回滚；不直接删库重建。Product/SKU/ProductSpecification按实际需要设计；BOM/零件批次/QC表不提前建设。消息/需求等关联同时校验对象项目，不仅验证最外层project_id。

## 11. 每步报告与停点

执行前：目标、前置、检查文件、拟修改文件、接口方案、权限、幂等、测试命令、预期、失败策略、验收条件、状态。

执行后：修改文件、关键代码、实际命令与输出、测试/失败、未知限制、用户需核对的一项动作。用户未确认通过前不打完成标记、不继续下一步。

协作实现按WORKSPACE_TASK_CHECKLIST.md的W0～W5与C01～C12验收。用户业务Step 1未确认就不进入行业Step 2。收到本Prompt后先复述当前活动步骤并提出一个小步骤方案，等待用户确认。

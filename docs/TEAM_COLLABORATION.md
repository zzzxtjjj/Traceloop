# TradeLoop 两人协作、验收与同步清单

Updated: 2026-10-25

## 1. 当前共同基线

两人开始并行开发前，必须都基于以下主分支提交：

```text
ccb3882 feat: implement evidence-driven business loops
```

该基线已经完成：证据底座、报价追溯、差评证据链、任务交付与人工验收、日报风险复盘、
规则来源校验、两条端到端测试、README 和模拟演示数据。

任何人开始工作前先执行：

```powershell
git checkout main
git pull --ff-only origin main
python -m pytest -q
python -m ruff check core services pages scripts tests
```

预期基线结果：44 个测试通过，Ruff 无错误。若基线不通过，不要继续叠加功能，先在群里同步错误。

## 2. 分工原则

- 甲负责“数据正确性与服务层”，乙负责“用户工作流与演示交付”。
- 同一时段不要同时修改同一个文件；确需修改时，先在群里声明文件和预计结束时间。
- SQLite 数据库、`.env` 和上传文件不共享；代码、测试、规则定义和模拟 CSV 通过 GitHub 共享。
- 每个小提交必须只包含一个可解释的变化，并附相应测试。
- 两人都不得在业务代码、提交信息、截图或文档中写入真实 API Key、真实访问码或客户数据。

## 3. 甲：后端、证据与安全负责人

建议分支：`feature/backend-ai-access`

### A1. 真实模型提供器（优先）

主要文件：

- `services/ai_service.py`
- 新增 `services/model_provider.py`
- `core/config.py`
- `prompts/review_classify_v1.txt`
- `tests/test_ai_service.py`
- 新增 `tests/test_model_provider.py`

具体任务：

- 只从环境变量读取 API Key、模型名、超时和基础 URL。
- 将模型响应送入已有 Pydantic Schema；禁止绕过 `run_structured_model`。
- 超时、网络错误、无效 JSON、缺字段分别返回可理解错误。
- 保留 AiRun 的成功/失败、输入哈希、模型名、Prompt 版本和延迟。
- 评价分类只返回主题、评价 ID、原文连续片段、置信度、缺失信息和替代解释。
- 模型不得返回统计总数作为最终事实；数量和占比继续由程序聚合。
- 没有 API Key 时继续使用明确标记的 rule-based 降级，不伪装为 AI。

完成标准：

- 假模型单元测试覆盖成功、修复重试、超时和永久无效结构。
- 至少用一份模拟评价 CSV 跑通真实/沙盒模型；输出中的评价 ID 和原文片段均能校验。
- Key 不出现在 `git diff`、日志或截图中。

完成 A1 后先提交：

```powershell
git add services/ai_service.py services/model_provider.py core/config.py prompts tests
git commit -m "feat: connect validated structured model provider"
git push -u origin feature/backend-ai-access
```

### A2. 数据库迁移与旧数据兼容

主要文件：

- 新增迁移目录和配置（建议 Alembic）
- `core/db.py`
- `core/models.py`
- 新增迁移测试

具体任务：

- 为当前新增表生成初始迁移，不删除现有 SQLite 数据。
- 在空数据库和已有第一阶段数据库上分别执行升级测试。
- 给迁移失败提供备份提示，不在脚本中自动删除数据库。
- 记录迁移版本；启动时不要静默假装数据库已升级。

完成标准：空库升级、旧库升级、重复升级三种测试均通过。

完成 A2 后提交：

```powershell
git add core migrations tests
git commit -m "feat: add additive database migrations"
git push
```

### A3. 真实成员与项目权限最小版

主要文件：

- `core/models.py`
- `services/project_access.py`
- `services/project_service.py`
- 新增权限测试

具体任务：

- 增加 User、ProjectMember 或等价最小模型。
- 区分查看、执行、审核、项目管理权限。
- 所有按 ID 获取 Artifact、Evidence、Finding、Task、ReviewBatch 的服务都校验项目成员关系。
- 访问码只负责加入/解锁项目，不直接等于负责人权限。
- URL、文件 ID 或 Artifact ID 不能绕过项目权限。

完成标准：跨项目读取、越权审核、越权任务发布和猜测 ID 均有失败测试。

## 4. 乙：页面、演示与产品交付负责人

建议分支：`feature/ui-demo-polish`

### B1. AI 结果页面接入

主要文件：

- `pages/04_差评改进.py`
- `pages/05_本地化与校验.py`
- 必要时新增 UI 辅助函数，但不要修改甲正在改的 provider 文件

具体任务：

- 在差评页明确显示分类方式：真实模型、规则降级或失败。
- 显示模型运行 ID、Prompt 版本、证据引用、缺失信息和人工审核状态。
- 模型失败时保留原批次，不写入半成品 Finding，并提供重试入口。
- 本地化页接入英/德 V1、用户反馈、V2 和版本差异；版本内容必须持久化到 Generation。
- 规则校验仍调用程序逻辑，不允许模型直接给“合规通过”。

完成标准：无 Key、模型成功、模型失败三种页面状态均可演示；页面用语不夸大能力。

完成 B1 后提交：

```powershell
git add pages core/theme.py tests
git commit -m "feat: expose reviewed AI workflow in Streamlit"
git push -u origin feature/ui-demo-polish
```

### B2. 演示数据与路演脚本

主要文件：

- `data/demo/`
- `scripts/seed_demo.py`
- 新增 `docs/DEMO_RUNBOOK.md`
- `README.md`

具体任务：

- 明确标注所有模拟数据，不混入真实客户、员工或供应商敏感信息。
- 准备一份正常报价、一份缺字段报价、一份混合币种报价。
- 准备改进前/后评价、重复评价、缺生产批次评价。
- 写 8–10 分钟演示台词：报价证据链约 3 分钟，差评改进闭环约 4 分钟，限制说明约 1 分钟。
- 给每个页面准备失败演示和恢复步骤。

完成标准：在全新临时数据库执行 `seed_demo.py` 后，两条工作流无需手工改库即可演示。

### B3. 验收体验和交付清单

主要文件：

- 页面文案和布局
- `docs/IMPLEMENTATION_STATUS.md`
- `README.md`

具体任务：

- 统一状态中文：草稿、待执行、执行中、被阻塞、待验收、已完成。
- 每个危险或不可逆操作增加说明；导入、审核、发布和验收成功后给清晰反馈。
- 检查小屏幕、空数据、重复点击和页面刷新。
- 维护已完成/未完成/模拟数据/真实能力四类交付说明。

## 5. 两人共同完成的里程碑与 commit 门槛

“一起 commit”不是两人同时编辑一个提交，而是：各自在功能分支完成小提交，达到共同门槛后再把
两个分支合并到 `main`，形成双方都验收过的同步点。

### 同步点 M1：真实 AI 最小闭环

甲完成 A1，乙完成 B1 后，双方共同执行：

- 一条评价能由模型返回结构化分类。
- 评价 ID 和原文片段校验通过。
- 程序统计与分类明细数量一致。
- 模型失败不产生关键业务状态。
- 人工可以接受、修改或驳回 Finding。

两人都签字确认后合并 PR，并在 `main` 产生里程碑提交：

```text
feat: complete reviewed AI analysis milestone
```

### 同步点 M2：身份和数据库兼容

甲完成 A2/A3，乙完成 B3 中的登录、越权和空数据页面验收后，共同执行：

- 旧数据库可升级且记录不丢失。
- 用户只能查看所属项目。
- 普通岗位不能发布任务或验收自己的交付。
- 猜测文件、批次、任务 ID 无法跨项目读取。

共同合并后的里程碑提交：

```text
feat: complete project membership and migration milestone
```

### 同步点 M3：黑客松交付冻结

两人停止加功能，只做以下共同检查：

```powershell
git checkout main
git pull --ff-only origin main
python scripts\seed_demo.py
python -m pytest -q
python -m ruff check core services pages scripts tests
streamlit run app.py
```

共同手工验收：

- 报价 → Evidence/Finding → 人工 Decision → Task → 交付 → 验收。
- 评价 A → Evidence/Finding → Task → 验收 → 评价 B → 同口径复检。
- 项目越权、重复导入、模型失败、规则无来源、任务缺材料五种异常。
- README、实施状态、演示台词与页面表述一致。

共同冻结提交：

```text
release: freeze TradeLoop hackathon demo
```

随后打标签：

```powershell
git tag -a v1.0.0-demo -m "TradeLoop hackathon demo"
git push origin main --tags
```

## 6. 每日同步操作

开始工作：

```powershell
git checkout main
git pull --ff-only origin main
git checkout <自己的分支>
git merge main
```

结束一个可测试小模块：

```powershell
python -m pytest -q
python -m ruff check core services pages scripts tests
git status --short
git add <本模块文件>
git commit -m "feat: <一个明确结果>"
git push
```

不要使用 `git add .` 把 `.env`、临时截图、个人笔记或数据库一起提交。提交前双方都检查：

```powershell
git diff --cached --stat
git diff --cached
```

## 7. 冲突处理

- 出现冲突时，先停止继续编辑，在群里发出文件名和冲突分支。
- 由该文件当前负责人解决冲突，另一人只负责复核结果。
- 不使用 `git reset --hard` 或强制推送共享分支。
- 不直接向 `main` 强推；使用 Pull Request，并要求另一人 review。
- 合并后双方立即切回 `main` 并 `git pull --ff-only`，确认提交哈希一致。

## 8. Pull Request 模板

每个 PR 至少写明：

- 完成了什么业务结果。
- 修改了哪些核心文件。
- 实际运行了哪些测试及结果。
- 是否改变数据库结构、环境变量或演示数据。
- 哪些结论仍来自模拟数据或规则降级。
- 需要另一人重点检查的页面或风险。

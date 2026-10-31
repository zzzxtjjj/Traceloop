# TradeLoop 两人协作、验收与同步清单

## 2026-10-31 项目工作空间补充（当前范围）

最新范围和多人验收以 [工作空间架构](PROJECT_WORKSPACE_ARCHITECTURE.md) 与 [W0～W5/C01～C12清单](WORKSPACE_TASK_CHECKLIST.md) 为准。本文后面的日期、测试基线和旧M节点为历史参考，不据此把新增功能勾成完成。

甲新增负责：可信身份与项目隔离、群聊持久消息、文件存储和授权下载、解析与证据定位、岗位需求、AI任务草稿及人工发布、DailyUpdate契约和AI项目复盘。优先复用现有模型。

乙新增负责：项目工作空间概况、群聊与刷新、文件上传/预览/下载、AI提取结果、需求与任务草稿审核、任务中心、每日汇报、项目复盘、邀请与权限展示，以及使用教学。

双方先确认接口、岗位与权限、幂等和文件边界；core主题、模型、Schema、配置、依赖、规则和README为协调文件。每个小模块先各自测试commit、互审，再合并集成分支；最终才进main。当前有未提交内容，不自动切换甲方目标分支feature/backend-ai-access。

分别使用 [甲方执行Prompt](PARTNER_A_EXECUTION_PROMPT.md) 和 [乙方执行Prompt](PARTNER_B_EXECUTION_PROMPT.md)。坚持先方案、用户确认后实施、用户验收后进入下一步。当前业务活动Step 1不变；本轮不开发、不迁移、不调用真实模型。

Updated: 2026-10-29

## 1. 当前集成基线

当前共同检查分支：

```text
integration/parallel-progress-20261029
```

当前验证结果：

```text
174 tests passed
Ruff passed
```

这只是集成分支基线。双方完成代码审查、页面验收和文档核对后，才将它合并到 `main`。两台电脑必须以合并后的同一个 `main` 提交哈希开始下一阶段。

同步和检查命令：

```powershell
git fetch origin
git checkout integration/parallel-progress-20261029
git pull --ff-only
python -m pytest -q
python -m ruff check core services pages scripts tests
git rev-parse HEAD
```

## 2. 文件所有权

### 甲负责后端和数据正确性

甲负责：

- `core/`
- `services/`
- `scripts/seed_demo.py`
- 服务层和端到端测试
- 数据库结构、Alembic 迁移和项目访问边界
- 模型提供器、结构化输出校验和错误处理
- 跨模块证据链查询

甲的结果标准：算得对、存得住、查得回、失败不污染、不能跨项目越权。

### 乙负责页面和演示交付

乙负责：

- `pages/`
- `data/demo/`
- 页面测试和演示流程测试
- `docs/DEMO_RUNBOOK.md`
- `docs/THIRD_PARTY_COMPONENTS.md`
- `docs/PLATFORM_EXPORT.md`
- `deliverables/`

乙的结果标准：看得懂、点得通、错误有提示、模拟数据标记清楚、现场能够恢复。

### 共同文件

以下文件必须先在聊天中声明再修改，不能两人同时编辑：

- `README.md`
- `requirements.txt`
- `core/models.py`
- `core/schemas.py`
- `core/config.py`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/TEAM_COLLABORATION.md`
- `docs/两人分工执行表.md`

`scripts/seed_demo.py` 归甲维护。乙只维护 `data/demo/`，如模拟数据要求脚本变化，应把数据文件、预期导入结果和错误信息发给甲。

## 3. 当前已完成能力

双方不要重复开发以下内容：

- 报价 CSV 校验、混合币种阻止、确定性比较、原始字段 Evidence、风险 Finding 和人工供应商决定。
- 评价导入、评价 ID 去重、批次元数据、程序统计、原文 Evidence 和人工 Finding 审核。
- Finding 转任务草稿、人工发布、交付 Evidence、接受或驳回验收。
- 日报、阻塞、逾期和缺材料提醒。
- 改进前后批次同口径比较，并显示样本量和非因果限制。
- Finding 到原始 Evidence、任务、交付审核、改进记录和后续复检的跨模块查询。
- US/DE V1、反馈、V2、父版本和规则结果持久化。
- OpenAI-compatible 模型适配器、结构校验和 401/429/5xx/超时错误映射的模拟测试。
- 正常和异常模拟 CSV、演示运行手册、平台配置说明、第三方组件声明。
- 五页离线路演 HTML 和 800mm × 1800mm SVG 海报骨架。
- Python 3.12 GitHub Actions，自动运行 pytest 和 Ruff。
- Alembic 非破坏迁移，覆盖空数据库、受支持的旧数据库和重复升级。
- 统一安全权限/异常 UI，敏感页面使用一致的角色边界提示和脱敏错误信息。
- User/ProjectMember 持久化、成员项目列表隔离、负责人添加成员和停用状态拒绝。
- 正确访问码不授予成员资格；非成员仍会被 `require_project_member` 拒绝。
- 模型输入字符数/评价数预算和 `MODEL_MAX_ATTEMPTS=1` 默认单次请求策略。
- 默认离线模型配置检查；截至本轮未配置环境的状态为未配置且未 live 验证。
- 离线发布检查 quick、`--json`、`--full`；最终推送后预期 quick/JSON 为 9 pass、1 warning、0 fail，full 为 11 pass、1 warning、0 fail，必须重新实测。唯一预期 warning 为模型未配置。
- 海报可复现 SVG 二维码已指向 GitHub 仓库；两部手机扫码和仓库公开访问仍待人工验收。

## 4. 仍未完成或必须继续验证

### A1 真实模型现场验证

负责人：甲为主，乙验收页面。

当前状态：模型适配器和模拟 HTTP 测试已完成；真实联网调用尚未验证。

先阅读 [模型 API 本地配置与安全检查](MODEL_API_SETUP.md)。默认运行 `python scripts\check_model_api.py` 只做离线检查；截至本轮未配置环境，实际结果为 `configured=false`、`live_verified=false`、缺少 `MODEL_API_KEY,MODEL_NAME`，退出码 `1` 属配置前预期状态，不是故障，以后应以新一次检查为准。输入预算已启用，`MODEL_MAX_ATTEMPTS` 默认 `1`。

启动、CI、测试和演示流程绝不自动运行 `--live`。只有用户提供真实配置并明确允许一次 live 请求后，操作者才可手动执行。

完成条件：

- [ ] 密钥只存在于本机或部署 Secret。
- [ ] 真实或官方沙盒调用返回结构化结果。
- [ ] 返回的评价 ID 和原文连续片段通过本地校验。
- [ ] 超时、401、429 和服务端错误有明确页面反馈。
- [ ] 模型失败不写入 Finding。
- [ ] 页面准确显示真实模型、规则降级或失败，不能混淆。

未完成这些检查前，不得在 README、海报或路演中说“真实 AI 已上线”。

### A2 版本化数据库迁移（已完成）

负责人：甲。

当前状态：已完成 Alembic 基线和非破坏升级路径，空数据库、受支持的旧数据库、重复升级和失败提示均有自动测试。迁移不会把备份责任或任意生产数据库兼容性自动变成已解决能力。

本机 `data/tradeloop.db` 已升级至 `0002_project_membership`。迁移前备份仅保存在本机，并由 `.gitignore` 排除，不得加入提交或交付包。

验证结果：迁移不自动删除现有数据；失败时提示迁移失败、未自动删除数据和备份要求。

### A3 项目成员权限（持久化与服务校验已完成）

负责人：甲负责后端，乙负责权限和异常页面。

当前状态：User/ProjectMember 持久化、成员列表隔离、owner 添加成员、成员唯一性和停用状态拒绝已完成。访问码与成员资格相互独立。

边界：本地用户选择只是演示身份上下文，不是登录认证；服务层传入 user ID 也不是不可伪造的生产会话。OAuth/SSO、服务端认证会话、完整成员生命周期和企业级 RBAC 仍未完成。

### B4 统一安全权限与异常 UI（已完成）

负责人：乙。

已完成：

- [x] 访问码错误、项目权限不足和敏感对象访问使用统一、安全的反馈。
- [x] 模型未配置、模型错误、规则错误和数据校验错误使用可操作且脱敏的提示。
- [x] 报价、任务、差评和本地化敏感页面接入统一角色边界说明与异常渲染。
- [x] 自动测试确认页面可加载，错误信息不会泄露对象、上游响应或本地路径。

边界：该 UI 层改善反馈并配合 User/ProjectMember 服务校验，但不等于生产登录认证、可信会话或企业级 RBAC。

### B5 最终交付

负责人：乙准备，甲核对技术真实性。

完成条件：

- [ ] 在最终代码上连续完成三次三分钟路演。
- [x] 可复现 SVG 二维码已指向 `https://github.com/zzzxtjjj/Traceloop`。
- [ ] 使用两部手机扫码，并在未登录环境确认仓库公开可访问。
- [ ] 按主办方规格导出 800mm × 1800mm 海报。
- [ ] README、实施状态、运行手册、路演和页面描述一致。
- [ ] 新电脑从 clone 到启动不超过十分钟。

## 5. 共同同步点

最终联合操作统一从[一次性批量验收清单](BATCH_ACCEPTANCE.md)进入；独立复核可使用 [Chat 模式验收 Prompt](CHAT_MODE_REVIEW_PROMPT.md)，桌面副本无需记录绝对路径。历史[干净克隆复演](CLEAN_CLONE_REHEARSAL.md)基于 `dc430c4` 和 158 项测试，只证明当时的远程 HEAD；最终候选必须按当前 174+ 基线重新复演。

### M0 架构和文件边界

进入条件：双方阅读当前架构、实施状态和本清单。

通过条件：能够共同描述完整链路：问题产生、原始证据、人工确认、任务、交付验收和后续复检；文件所有权没有冲突。

### M1 模型闭环

进入条件：甲完成真实模型验证；统一页面状态与异常 UI 已完成。

通过条件：真实调用、证据引用、本地统计、失败安全和人工审核全部通过。只有这一步完成后才能更新“真实 AI”对外表述。

### M2 数据库和成员权限

当前状态：Alembic 非破坏迁移和成员最小版均已完成；生产登录认证与企业级 RBAC 未完成。

通过条件：空库、受支持旧库、重复升级、非成员访问、普通成员加人、owner 加人、成员唯一性和停用状态均已通过；生产会话、OAuth/SSO 和企业级 RBAC 留作后续生产化工作。

### M3 最终交付冻结

进入条件：两条工作流、异常演示、交付材料和能力边界均完成。

共同执行：

```powershell
git checkout main
git pull --ff-only origin main
python scripts\migrate_db.py
python scripts\seed_demo.py
python -m pytest -q
python -m ruff check core services pages scripts tests
streamlit run app.py
```

共同验收：

- [ ] 报价到交付验收完整跑通。
- [ ] 差评到任务、验收和下一批复检完整跑通。
- [ ] 缺字段、混合币种、重复评价和缺关联异常符合预期。
- [ ] 模型未配置或失败不污染业务状态。
- [ ] 页面和服务均阻止跨项目访问。
- [ ] 所有模拟数据、真实能力和未完成限制已标明。
- [ ] README、海报、路演和实施状态与最终代码一致。
- [ ] 两台电脑上的测试和提交哈希一致。

最终标签：

```powershell
git tag -a hackathon-final -m "TradeLoop hackathon final submission"
git push origin main hackathon-final
```

`v1.0.0-demo` 可以作为额外版本标签，但不能替代 `hackathon-final`。

## 6. 每日同步和提交

开始工作：

```powershell
git checkout main
git pull --ff-only origin main
git checkout <自己的分支>
git merge main
```

完成一个小模块：

```powershell
python -m pytest -q
python -m ruff check core services pages scripts tests
git status --short
git add <本模块文件>
git diff --cached
git commit -m "feat: <一个可验证结果>"
git push
```

禁止使用 `git add .`、`git reset --hard`、共享分支强推或直接在 `main` 开发。`.env`、SQLite 数据库、上传文件、真实客户数据和 API Key 不得进入 Git。

## 7. Pull Request 门槛

每个 PR 必须写明：

- 完成的业务结果和修改文件。
- 实际运行的测试及结果。
- 是否改变数据库、环境变量、模拟数据或交付物。
- 哪些能力仍然是规则降级、模拟数据或未完成状态。
- 需要另一人重点手工检查的页面和异常。

合并后双方立即执行：

```powershell
git checkout main
git pull --ff-only origin main
git rev-parse HEAD
```

两边提交哈希一致后，下一阶段才能开始。

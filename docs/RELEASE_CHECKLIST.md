# TradeLoop 最终发布与联合验收清单

> 适用分支：`integration/parallel-progress-20261029` 合并至 `main` 前
>
> 使用方式：甲乙共同操作；只有全部强制项通过，才允许创建 `hackathon-final` 标签。
>
> 当前自动测试下限：174 项。后续可以增加，但不得减少或跳过失败项。
>
> 当前标签状态：`hackathon-final` 禁用。先按 [发布缺口矩阵](RELEASE_GAP_MATRIX.md) 完成无需 API、真实 API（如对外宣称）和现场人工验收门禁。
>
> 一次性执行入口：[批量验收清单](BATCH_ACCEPTANCE.md)。
>
> 独立复核入口：[Chat 模式独立验收 Prompt](CHAT_MODE_REVIEW_PROMPT.md)。桌面副本可保持同名，无需记录绝对路径。

## 0. 发布原则

- [ ] 本次验收使用准备提交的同一个 commit，不在验收途中临时改代码或数据。
- [ ] 甲乙双方本地 `HEAD` 完全一致。
- [ ] API Key、项目访问码、真实个人信息、`.env` 和本地秘密未进入 Git 或交付包。
- [ ] 模拟数据、真实联网能力和未完成功能均有明确声明，不把演示结果描述为真实客户事实。
- [ ] 所有失败项都有负责人和处理结论；不得用口头承诺代替验收。

## M0：架构、范围与文件所有权确认

- [ ] 两人能共同说明链路：业务问题 → 原始证据 → 人工确认 → 改进任务 → 交付物 → 人工验收 → 后续复检。
- [ ] 甲负责后端、数据库、AI 边界和 `scripts/seed_demo.py`。
- [ ] 乙负责 `pages/`、`data/demo/`、演示材料和最终交付物。
- [ ] 共享文件的改动已由另一人复核，没有覆盖对方尚未合并的修改。
- [ ] 已阅读 [当前实现状态](IMPLEMENTATION_STATUS.md)、[团队协作清单](TEAM_COLLABORATION.md)和[两人分工执行表](两人分工执行表.md)。

通过标准：两人对已实现、未实现和演示范围的表述一致。User/ProjectMember 最小权限已经实现；真实模型联网、生产登录会话和企业级 RBAC 不得误报为已完成。

## M1：自动验证与页面检查

### 1. 安装与自动测试

在仓库根目录执行：

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m ruff check core services pages scripts tests
```

- [ ] `pytest` 显示不少于 174 项测试且全部通过。
- [ ] Ruff 显示 `All checks passed!`。
- [ ] CI 使用 Python 3.12，安装 `requirements.txt` 后执行相同的 pytest 和 Ruff 命令。
- [ ] 没有通过跳过测试、删除断言或忽略规则来制造绿色结果。

### 2. 所有 Streamlit 页面

```powershell
python scripts\migrate_db.py
python scripts\seed_demo.py
streamlit run app.py
```

- [ ] `app.py` 能启动，终端没有未处理异常。
- [ ] `01_项目首页.py`：项目创建、切换、访问码和项目概览可用。
- [ ] `02_报价决策.py`：报价导入、标准化、风险证据和任务创建可用。
- [ ] `03_任务与日报.py`：任务状态、交付物、验收和日报核对可用。
- [ ] `04_差评改进.py`：评价导入、统计、证据、人工审核、任务和复检可用。
- [ ] `05_本地化与校验.py`：美国/德国版本和规则来源校验可用。
- [ ] 每个页面刷新一次后仍可使用，不出现白屏、对象丢失或跨项目数据泄露。
- [ ] 无权限、缺失字段、重复导入、样本不足、AI 未配置和规则降级都有可理解的提示。

通过标准：174+ 测试和 Ruff 通过，全部页面逐页人工检查通过。

### 3. 成员权限与认证边界

- [ ] User/ProjectMember 记录可以持久化，用户项目列表不包含非成员项目。
- [ ] owner 可以添加成员，普通成员不能添加；重复成员、停用用户和停用成员均被拒绝。
- [ ] 输入正确访问码后，非成员仍不能通过 `require_project_member`。
- [ ] 页面拒绝信息不泄露项目名称、用户信息、对象 ID 或本地路径。
- [ ] 演示明确说明：本地用户选择不是登录认证，服务级 user ID 传递不是生产会话。
- [ ] OAuth/SSO、可信服务端认证会话和企业级 RBAC 标记为未完成。

## M2：两条端到端工作流与异常恢复

### 工作流 A：供应商报价到任务验收

- [ ] 导入正常报价并确认价格、币种、单位、MOQ、交期和付款条件。
- [ ] 导入“报价缺字段”样本，页面准确指出缺失字段，不补造信息。
- [ ] 导入“混合币种”样本，系统拒绝无依据的直接价格排名。
- [ ] 从报价风险查看原始字段或来源证据。
- [ ] 将待确认事项创建为任务，填写责任岗位、交付物、截止日期和验收标准。
- [ ] 缺少交付物时不能通过验收；补充材料后由人工确认。

通过标准：从风险结论可以回到原始报价，再追踪到任务、交付物和人工验收记录。

### 工作流 B：差评到改进复检

- [ ] 导入首批评价，显示总数、类别、占比、时间范围和样本限制。
- [ ] 重复导入相同评价时不重复计数，并显示重复处理结果。
- [ ] 对缺少订单、批次或供应商关联的评价显示“待确认”或“证据不足”。
- [ ] 查看原始评价、统计依据、模型假设、缺失信息和人工审核结论。
- [ ] 从问题创建改进任务，提交交付物并完成人工验收。
- [ ] 导入下一批评价，用一致口径展示样本量和前后变化，并关联此前任务。
- [ ] 页面不把评价占比称为真实故障率，也不单凭指标变化宣称措施有效。

通过标准：从一条差评可追溯到原文、问题、证据、任务、验收和下一批复检；缺失关系明确显示，不生成虚假关联。

### 真实模型联网与降级状态

- [ ] 已阅读 [模型 API 本地配置与安全检查](MODEL_API_SETUP.md)。
- [ ] 默认离线命令 `python scripts\check_model_api.py` 不发起外部请求。
- [ ] 截至本轮未配置环境的离线结果已记录：`configured=false`、`live_verified=false`、缺少 `MODEL_API_KEY,MODEL_NAME`，退出码 `1` 属配置前预期状态，不算故障；以后以新一次检查为准。
- [ ] 输入字符数与评价数预算已启用，`MODEL_MAX_ATTEMPTS` 默认值为 `1`。
- [ ] 启动、CI 和演示流程绝不自动运行 `--live`；只有用户明确授权后才由操作者手动运行一次。
- [ ] 记录本次是否实际完成真实模型联网验证：`已验证 / 未验证`。
- [ ] 若已验证：仅使用脱敏小样本，记录模型名称、Prompt 版本、耗时和结果状态，不记录密钥。
- [ ] 若未验证：页面和路演明确说明当前仅验证了适配器、结构校验和模拟 HTTP 测试。
- [ ] 删除 API Key 后重启，系统能进入明确的未配置或规则降级状态，不白屏、不污染关键业务记录。
- [ ] 模型超时、无效 JSON 或 API 错误时，用户得到可操作提示，人工流程仍可继续。

通过标准：真实联网是否完成有准确记录；API Key 缺失和调用失败均能安全降级。

## M3：新电脑、交付物与最终冻结

### 1. 全新电脑 10 分钟启动

在未使用过本项目的电脑上计时：

```powershell
git clone https://github.com/zzzxtjjj/Traceloop.git
cd Traceloop
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\migrate_db.py
python scripts\seed_demo.py
streamlit run app.py
```

- [ ] 从开始克隆到浏览器出现可操作首页不超过 10 分钟。
- [ ] 记录电脑系统、Python 版本、开始时间、完成时间和遇到的问题。
- [ ] 重启 Streamlit 后演示数据、任务、证据和复检记录仍能读取。
- [ ] 若网络安装时间导致超时，必须记录实际耗时和离线依赖方案，不能直接勾选通过。
- [ ] 本机 `data/tradeloop.db` 显示迁移版本 `0002_project_membership`。
- [ ] 迁移前备份只保存在本机，数据库和备份文件均未进入 Git 或交付包。

### 2. 模拟数据和安全声明

- [ ] 页面、海报和路演均明确标注演示数据为模拟数据。
- [ ] 不展示真实客户姓名、电话、地址、API Key、访问口令或本地文件绝对路径。
- [ ] 演示结论不被表述为真实供应商责任、产品故障率或已证明的改进效果。
- [ ] [演示运行手册](DEMO_RUNBOOK.md)、[平台配置说明](PLATFORM_EXPORT.md)和[第三方组件声明](THIRD_PARTY_COMPONENTS.md)已复核。

### 3. 0.8 m × 1.8 m 海报

- [ ] 打开 `deliverables/poster/tradeloop_poster.svg`，确认 `width="800mm"`、`height="1800mm"`。
- [ ] 最终导出文件的物理尺寸仍为 0.8 m × 1.8 m，没有被缩放成普通 A4 页面。
- [ ] 海报包含问题、两条证据链、核心能力、安全边界和模拟数据声明。
- [x] 可复现 SVG 二维码已指向 `https://github.com/zzzxtjjj/Traceloop`，自动结构与目标测试通过。
- [ ] 使用至少两部手机实际扫码，并在未登录/无缓存环境确认仓库公开可访问。
- [ ] 海报没有伪造产品截图、测试数字、客户名称或合作方标志。

尺寸检查命令：

```powershell
Select-String -Path .\deliverables\poster\tradeloop_poster.svg -Pattern 'width="800mm"','height="1800mm"','viewBox="0 0 800 1800"'
```

### 4. 三分钟路演

- [ ] 双击打开 `deliverables/pitch/index.html`，断网时五段导航仍可使用。
- [ ] 按 `deliverables/pitch/THREE_MINUTE_SCRIPT.md` 完整彩排至少两次。
- [ ] 每次计时不超过 180 秒，且两条端到端链路都被清楚说明。
- [ ] 路演准确区分确定性统计、AI 假设、人工审核和未知信息。
- [ ] 准备页面故障时可使用的离线 HTML/PDF 备用材料。

通过标准：新电脑 10 分钟启动、交付物齐全、海报尺寸正确、二维码可扫、路演不超过三分钟。

## 最终 Git 同步与标签门禁

甲乙分别执行并交换输出：

```powershell
git fetch origin
git status --short
git rev-parse HEAD
git rev-parse origin/main
python -m pytest -q
python -m ruff check core services pages scripts tests
```

- [ ] 双方 `git status --short` 均为空。
- [ ] 双方 `git rev-parse HEAD` 输出完全一致。
- [ ] 准备发布的 `HEAD` 与 `origin/main` 一致。
- [ ] 双方机器均通过 174+ 测试和 Ruff。
- [ ] 最终推送后重新实测：quick/JSON 为 9 pass、1 warning、0 fail，`--full` 为 11 pass、1 warning、0 fail；唯一 warning 为模型未配置。
- [ ] 已阅读[干净克隆复演记录](CLEAN_CLONE_REHEARSAL.md)：该记录基于 `dc430c4` 和 158 项测试，最终候选已重新复演。
- [ ] M0、M1、M2、M3 全部强制项已通过并由两人签字确认。
- [ ] 最终交付文件已打开检查，而不是仅确认文件存在。

当前不得执行以下命令。只有上述项目和发布缺口矩阵全部通过后，由一人执行、另一人现场复核：

```powershell
git switch main
git pull --ff-only
git tag -a hackathon-final -m "TradeLoop hackathon final submission"
git push origin main hackathon-final
```

禁止提前创建 `hackathon-final`。如果最终验收后又修改任何代码、数据或交付材料，必须删除本地未推送标签或创建新的候选 commit，重新执行受影响的验收项后再打最终标签。

## 联合签字

```text
最终 commit：
甲验收人 / 时间：
乙验收人 / 时间：
自动测试数量：
真实模型联网状态：已验证 / 未验证
新电脑启动耗时：
海报二维码扫码结果：
三分钟路演实测时长：
hackathon-final 标签创建人 / 时间：
```

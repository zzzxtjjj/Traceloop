# TradeLoop Hackathon V1

TradeLoop 是一个证据驱动的跨境业务协作工作台。V1 将供应商报价、差评原文、人工审核、
改进任务、交付验收、日报和后续复检连接在同一项目内；程序负责统计和规则检查，模型接口
只接受结构化输出，关键业务状态必须由人工确认。

## 已实现

- 项目创建、切换、访问码哈希校验与项目级页面访问边界。
- 报价 CSV 校验、SHA-256 去重、币种可比性检查、确定性评分和来源证据。
- 报价风险回指原始行、缺失条件提示、供应商澄清问题和人工最终选择。
- 评价 CSV 字段校验、文件/评价 ID 去重、批次和时间范围记录。
- 规则分类（明确标记为 rule-based）、主题统计、原文 Evidence、Finding 和人工审核。
- 从已审核 Finding 创建任务草稿；项目负责人确认后才发布。
- 任务状态、岗位约束、交付 Evidence、人工验收和驳回补充。
- 日报关联任务；阻塞、逾期、缺日报和缺验收证据的确定性复盘。
- 基线/后续评价同口径比较，并明确“评价占比不是实际故障率、变化不证明因果”。
- 美国/德国规则检查，区分平台政策、消费者信息规则和内部采购标准，保存来源与版本。
- AI 结构化输出验证、一次修复重试、超时和无效 JSON 错误处理（真实模型供应商尚未配置）。

详细完成度与限制见 [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)。
两人分工、同步点和共同提交门槛见 [docs/TEAM_COLLABORATION.md](docs/TEAM_COLLABORATION.md)。
更直接的逐项执行表见 [docs/两人分工执行表.md](docs/两人分工执行表.md)。

## 项目结构

```text
hackson/
├─ app.py
├─ pages/                    # Streamlit 页面，只处理交互
├─ core/                     # 配置、数据库、模型、Schema、错误与共享 UI
├─ services/                 # 可测试的业务逻辑
├─ data/demo/                # 明确标记为模拟的报价/评价演示数据
├─ data/rules.json           # 带来源类型和版本的规则定义
├─ docs/                     # 架构、安全、内部标准和实施状态
├─ prompts/                  # AI Prompt 版本管理约定
├─ scripts/seed_demo.py      # 可重复执行的演示数据初始化
└─ tests/                    # 确定性单元和端到端工作流测试
```

## Windows 启动

建议使用 Python 3.11 或 3.12。

```powershell
cd D:\hackson
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts\seed_demo.py
streamlit run app.py
```

打开终端显示的地址，通常为 `http://localhost:8501`。演示项目访问码为 `demo2026`。

## 自动检查

```powershell
python -m ruff check core services pages scripts tests
python -m pytest -q
```

## 两条核心验收工作流

### 工作流 A：报价到人工验收

1. 进入“报价决策”，导入报价或使用模拟批次。
2. 查看确定性排名、每家供应商的来源证据、风险命中和待澄清项。
3. 由项目负责人填写理由并确认供应商；不要把排名第一理解为自动决策。
4. 审核报价 Finding，创建并发布澄清任务。
5. 在“任务与日报”提交带引用的交付材料；负责人验收后任务才完成。

### 工作流 B：差评到改进复检

1. 在“差评改进”导入 `reviews_before.csv`，运行主题分析。
2. 打开包装破损 Finding，核对评价 ID、CSV 行号和原文引用。
3. 人工接受或修改结论，生成并发布改进任务。
4. 提交交付证据并由负责人验收。
5. 导入 `reviews_after.csv`，运行相同分类口径并比较两批数据。
6. 验证页面同时展示样本量、数量、占比变化与因果限制说明。

## 两台电脑协作

将仓库推送到 GitHub 后，两人各自 clone，同步时使用小分支，避免同时改同一页面：

```powershell
git checkout -b feature/review-evidence
git add .
git commit -m "feat: review evidence workflow"
git push -u origin feature/review-evidence
```

另一位可使用 `feature/task-acceptance`。通过 Pull Request 合并，合并前先运行全部测试；`.env`、
SQLite 数据库、上传文件和虚拟环境不会进入 Git。共享的是代码和演示 CSV，不是各自电脑上的数据库。

## 安全与边界

- V1 访问码使用 PBKDF2-SHA256 哈希且不记录明文，但它不是企业级身份系统。
- 页面按项目解锁，服务会校验项目归属；演示角色选择器不能替代真实成员认证/RBAC。
- API 密钥只从 `.env` 读取；数据库、上传文件和 `.env` 已被 `.gitignore` 排除。
- 上传内容只作为业务数据，不作为系统或开发指令执行。
- 规则检查不等于法律意见或平台最终审核。

正式安全方案见 [docs/ACCESS_SECURITY.md](docs/ACCESS_SECURITY.md)。

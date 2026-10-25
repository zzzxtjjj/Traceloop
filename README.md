# TradeLoop Hackathon V1

TradeLoop 是一个面向中小外贸团队负责人的 AI 项目工作台。当前提交完成了第一阶段：项目空间、报价 CSV 导入校验，以及可解释的供应商评分。

## 当前可验收功能

- 创建项目，目标市场支持美国和德国。
- 项目访问码使用 PBKDF2-SHA256 哈希保存，页面不会保存明文。
- 一键创建演示项目，访问码为 `demo2026`。
- 下载/上传报价 CSV，预览有效行和逐行错误。
- 阻止缺列、错误类型、重复供应商和混合币种进入数据库。
- 相同文件通过 SHA-256 去重。
- 自定义价格、MOQ、交期和质量风险权重。
- 确定性评分、排名、风险关键词和方法说明。
- SQLite 持久化；刷新页面后项目和报价仍存在。
- 任务、日报、差评、本地化页面及数据模型骨架。

## 项目结构

```text
hackson/
├─ app.py
├─ pages/                 # Streamlit 页面，只处理交互
├─ core/                  # 配置、数据库、模型、Schema、共享 UI
├─ services/              # 可测试的业务逻辑
├─ data/demo/             # 可提交的模拟演示数据
├─ prompts/               # 后续 AI Prompt 版本管理
├─ scripts/seed_demo.py   # 演示数据初始化
├─ tests/                 # 自动测试
├─ .env.example
└─ requirements.txt
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

打开终端中显示的地址，通常为 `http://localhost:8501`。

## 测试和代码检查

```powershell
pytest -q
ruff check .
```

## 第一阶段人工验收

1. 运行 `python scripts\seed_demo.py`，终端应显示项目 ID 和 `demo2026`。
2. 启动应用，打开“项目首页”，应看到“保温杯新品出海”。
3. 新开无痕窗口或刷新会话，进入项目时输入错误访问码，应被拒绝；输入 `demo2026` 应进入。
4. 打开“报价决策 → 比较与排名”，应看到 3 家供应商、各维度分数和总分图表。
5. 修改权重并保持总和 100，排名或分数应立即重新计算；总和不是 100 时应阻止比较。
6. 下载模板再上传，应出现 3 行预览；确认后写入数据库。
7. 将模板中的 `moq` 列删除后上传，应显示“缺少必填列”，且不能确认导入。
8. 将任意一家币种改为 `EUR`，应显示“请统一币种”。
9. 连续上传同一文件两次，不应产生两个相同批次。
10. 停止并重新启动 Streamlit，项目和批次仍应存在。

## GitHub 初始化

仓库已适合直接初始化。确认本地验收通过后执行：

```powershell
git init -b main
git add .
git commit -m "feat: bootstrap TradeLoop and supplier scoring"
git remote add origin <你的 GitHub 仓库地址>
git push -u origin main
```

`.env`、SQLite 数据库、上传文件和虚拟环境已在 `.gitignore` 中排除。

## 下一阶段

在报价排名之上接入单一模型 API：结构化决策摘要、证据引用、风险问题、负责人确认和任务草稿。评分仍由代码计算，模型不负责修改分数。


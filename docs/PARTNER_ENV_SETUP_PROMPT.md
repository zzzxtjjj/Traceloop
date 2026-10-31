# 发给同伴 AI 的环境配置提示词

请为 TradeLoop 配置独立开发环境，并实际验证。仓库为 https://github.com/zzzxtjjj/Traceloop.git，当前共同基线分支为 integration/parallel-progress-20261029。先检查 Git 状态，保留已有修改，不切换或覆盖有未提交工作的分支。

1. 使用 Python 3.11（甲方实际版本为 3.11.16），不要使用 Python 3.14 预览版。检查可用 Python 的完整路径；缺少 3.11 时安装受支持的 3.11 版本并报告精确版本。不要依赖甲方电脑的 D 盘路径。
2. 在项目内创建 `.venv-tradeloop`，不修改系统 Python 或其他项目环境。不要复制甲方虚拟环境，虚拟环境不可跨电脑搬运。
3. 使用该环境的 Python 执行 `python -m pip install -r requirements-lock.txt`。锁文件固定了甲方验证过的依赖版本。若文件缺失，先报告并向甲方取得最新文件，不自行换一组版本宣称相同。
4. 仅在 `.env` 不存在时从 `.env.example` 复制。保留现有配置，真实模型 Key 和模型名称留空；不执行任何 `--live` 请求。
5. 使用该环境依次运行 `python -m pip check`、`python scripts/migrate_db.py`、`python scripts/seed_demo.py`、`python -m pytest -q` 和 `python -m ruff check core services pages scripts tests`。任一步失败都报告真实错误，不删除测试或数据来通过检查。已有数据库先备份再迁移。
6. 执行 `python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false`。用本机浏览器打开 http://127.0.0.1:8501，检查健康地址 /_stcore/health 返回 200。
7. 演示访问码为 demo2026。核对首页及五个业务页面，模型未配置时应明确显示规则降级。
8. 不提交 `.env`、数据库、虚拟环境、上传文件和密钥。不要改业务代码、合并 main 或创建最终标签。
9. 输出环境验收报告：Git 分支与 HEAD、Python 版本与路径、锁文件安装结果、pip check、测试数量、Ruff、迁移版本、首页与健康检查，以及尚未验证项。不能把 HTTP 200 当作业务流程全部通过。

Windows 命令中的 `python` 请替换为 ` .\.venv-tradeloop\Scripts\python.exe`，无需激活环境。Mac/Linux 使用 `.venv-tradeloop/bin/python`；跨平台依赖差异必须明确报告。

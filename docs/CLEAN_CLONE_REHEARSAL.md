# TradeLoop 远程集成分支干净克隆复演记录

> 复演日期：2026-10-29（Asia/Shanghai）
>
> 远程仓库：`https://github.com/zzzxtjjj/Traceloop.git`
>
> 远程分支：`integration/parallel-progress-20261029`
>
> 克隆目录：`C:\Users\legion\Documents\Codex\2026-10-25\zhe\work\tradeloop_clean_rehearsal_20261029`

## 结论

远程集成分支可以在全新独立目录中完成克隆、独立虚拟环境创建、依赖安装、数据库迁移、演示数据初始化、自动测试、Ruff、离线模型配置检查和 Streamlit HTTP 健康检查。

- 最终 HEAD：`dc430c48569ec305e7be513c558865214349e831`
- Python：`3.12.10`
- 自动测试：`158 passed`
- Ruff：`All checks passed!`
- 数据库 revision：`0002_project_membership`
- Streamlit 首页 HTTP：`200`
- Streamlit 健康检查：`200`，响应 `ok`
- 离线模型状态：`configured=false`、`live_verified=false`、缺少 `MODEL_API_KEY,MODEL_NAME`
- 最终克隆工作树：干净；`.venv` 和本地数据库由 `.gitignore` 排除

本次没有运行 `--live`，没有发起真实模型请求，也没有使用或记录任何真实 API Key。

## 环境与范围

复演开始前，指定目录不存在。复演只在该目录中创建克隆、虚拟环境和本地数据库，没有删除或覆盖任何已有目录。

使用的关键命令：

```powershell
git clone --branch integration/parallel-progress-20261029 --single-branch https://github.com/zzzxtjjj/Traceloop.git <target>
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\migrate_db.py
.\.venv\Scripts\python.exe scripts\seed_demo.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check core services pages scripts tests
.\.venv\Scripts\python.exe scripts\check_model_api.py
.\.venv\Scripts\python.exe -m streamlit run app.py --server.headless=true --server.port=8765 --browser.gatherUsageStats=false
```

## 分步证据

| 步骤 | 结果 | 退出码 | 实测耗时 |
|---|---|---:|---:|
| 克隆指定远程分支 | 成功，分支名正确 | 0 | 3.61 秒 |
| 创建独立 `.venv` | 成功，Python 3.12.10 | 0 | 7.23 秒 |
| 安装 `requirements.txt` | 成功 | 0 | 78.76 秒 |
| 执行 Alembic 迁移 | 成功，升级到 `0002_project_membership` | 0 | 1.42 秒 |
| 初始化演示数据 | 成功，演示项目 ID 1 | 0 | 3.39 秒 |
| 运行 pytest | 158 项全部通过 | 0 | 13.35 秒 |
| 运行 Ruff | 全部通过 | 0 | 0.89 秒 |
| 离线模型配置检查 | 预期未配置状态 | 1（预期） | 0.52 秒 |
| Streamlit 启动至可检查 | 成功；保守记录不超过工具等待时间 | 运行中 | ≤ 10.2 秒 |
| 首页与健康 HTTP 检查 | 首页 200；健康 200 / `ok` | 0 | 0.15 秒 |
| 停止 Streamlit | 已发送中断并确认端口不可访问 | 0 | < 3 秒 |

上述可相加步骤约 2 分钟完成，不含人工发起下一条命令的间隔。依赖安装使用当时可用的包缓存和网络，其他电脑的下载耗时可能不同。

## 离线模型检查

执行默认离线命令后得到：

```text
configured=false
live_verified=false
missing=MODEL_API_KEY,MODEL_NAME
```

命令退出码为 `1`。按照 [模型 API 本地配置与安全检查](MODEL_API_SETUP.md)，这是配置前的预期安全状态，不是应用故障。规则降级和人工审核仍可使用。

本次明确没有执行：

```text
python scripts\check_model_api.py --live
```

fake transport、离线测试和本次配置检查均不能作为真实联网成功证据。

## Streamlit HTTP 证据

Streamlit 在端口 `8765` 启动后，执行本机 HTTP 检查：

```text
GET http://127.0.0.1:8765/                 -> 200
GET http://127.0.0.1:8765/_stcore/health   -> 200, ok
```

检查完成后已停止该 Streamlit 会话，并再次确认健康地址不可访问，没有保留后台服务。

## 发布含义与限制

- 本记录证明远程 HEAD `dc430c48569ec305e7be513c558865214349e831` 在本机干净克隆环境中的可安装、可迁移、可测试和可启动状态。
- 该历史复演仍保持 158 项测试记录；当前开发基线已提高，最终候选必须按 174+ 测试重新干净克隆复演。
- 本记录不证明其他尚未推送的本地修改，也不替代双方在最终候选 commit 上再次验收。
- HTTP 200 和健康响应证明服务启动，不等于五个页面的完整人工交互验收。
- 158 项测试与离线检查不等于真实模型 API live 验证。
- 依赖安装耗时受网络、缓存和电脑性能影响；全新电脑十分钟门槛仍需在最终现场环境计时。
- `hackathon-final` 标签仍禁用，必须完成发布缺口矩阵和最终现场验收后才能创建。

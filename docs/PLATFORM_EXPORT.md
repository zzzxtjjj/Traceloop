# TradeLoop 平台配置导出说明

本文件描述可安全提交的运行配置和复现步骤。它不是密钥文件，也不包含真实访问凭据、个人信息或本机数据库内容。

## 1. 运行平台

- 操作系统：Windows 10 或 Windows 11 演示环境。
- Python：建议 3.11 或 3.12。
- Web 框架：Streamlit。
- 数据库：本地 SQLite，默认路径为项目目录下 `data/tradeloop.db`。
- 应用入口：`app.py`。
- 页面目录：`pages/`。
- 默认本地地址：`http://localhost:8501`。

## 2. 环境变量模板

只提交 `.env.example`，不提交 `.env`。

| 变量 | 是否必需 | 用途 | 安全要求 |
|---|---|---|---|
| `MODEL_API_KEY` | 否 | 真实模型提供器凭据 | 只存本机或部署平台 Secret，不写入 Git、日志或截图 |
| `MODEL_NAME` | 否 | 模型名称 | 不得借名称伪装实际未发生的模型调用 |
| `DATABASE_URL` | 否 | 覆盖默认 SQLite 连接 | 不提交包含用户名、密码或公网地址的真实连接串 |

当前第一阶段功能在 `MODEL_API_KEY` 为空时仍可使用规则基线和确定性业务逻辑。页面必须明确显示模型未配置或规则降级。

## 3. 安全导出清单

允许提交：

- `requirements.txt`
- `.env.example`
- `README.md`
- `app.py`、`pages/`、`core/`、`services/`、`scripts/`
- `data/demo/` 中明确标记的模拟 CSV
- `data/rules.json` 及其来源和版本说明
- `docs/` 和 `deliverables/` 中的交付材料

禁止提交：

- `.env` 和任何 API Key
- `data/tradeloop.db` 或其他运行数据库
- `data/uploads/` 中的用户上传文件
- `.venv/`、缓存、日志和测试临时目录
- 真实客户、员工、供应商、订单、地址、电话或个人身份数据
- 本机绝对路径、浏览器 Cookie、Session 或访问令牌

## 4. 可复现启动

```powershell
git clone https://github.com/zzzxtjjj/Traceloop.git
cd Traceloop
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts\seed_demo.py
python -m pytest -q
streamlit run app.py
```

演示项目访问码由演示数据脚本输出。访问码只用于演示入口，不代表真实成员身份和企业级授权。

## 5. 提交前导出记录

最终提交时填写，不在仓库中保存秘密：

- Git 提交哈希：`待填写`
- Git 标签：`hackathon-final`
- Python 版本：`待填写`
- 依赖快照文件：`待导出或说明不提交的原因`
- 数据库迁移或初始化方式：`scripts/seed_demo.py` 与当前数据库方案
- 模型提供器状态：`未配置 / 已配置并验证`
- 演示数据状态：`模拟数据`
- 已知限制：见 `docs/IMPLEMENTATION_STATUS.md`

## 6. 部署边界

当前配置面向本地单机黑客松演示。正式部署仍需要 HTTPS、真实身份认证、服务端 Session、持久化限速、对象存储访问控制、备份、审计、数据库迁移和密钥管理。不得把本地演示配置描述为生产级安全方案。

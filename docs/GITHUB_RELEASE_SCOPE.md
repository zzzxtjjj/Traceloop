# GitHub 发布范围与项目说明

## 项目结构

- `app.py`：Streamlit 应用入口和登录后的默认页面。
- `pages/`：项目工作台、报价、任务与日报、客户反馈、项目交流、文档 AI、复盘和文件分拣界面。
- `core/`：配置、数据库、认证 UI、共享 Schema、主题、权限与结果展示。
- `services/`：认证、项目成员、报价与评价导入、文档解析、Evidence、AI Provider、任务、日报和产品身份服务。
- `migrations/`：Alembic 迁移。
- `prompts/`：有版本的模型提示词。
- `scripts/`：迁移、演示数据、备份/恢复、健康检查与受控验收脚本。
- `tests/`：服务、权限、解析器、数据库和页面回归测试。
- `data/acceptance/`：本机保存模拟验收夹具与经许可的公开资料；本次源码推送不包含数据目录。
- `deploy/`：Ubuntu systemd、Nginx 和 logrotate 示例配置。

## 已实现能力

- 邮箱密码认证、会话、邮箱验证/找回流程和项目成员权限检查。
- 项目工作台、项目交流、文件库、任务管理与日报、项目复盘。
- PDF、DOCX、XLSX、CSV、TXT、PNG/JPG 的解析入口；HTML 不再作为业务上传格式。
- 文档 AI 结构化分析、动态属性、授权 Evidence 校验和中文业务结果展示。
- AI 文件分拣建议及负责人审核后创建未发布任务草稿。
- 客户评价字段映射、重复检查、规则分析和来源 Evidence。
- 供应商字段映射、币种/价格/交期校验和确定性比较。
- DeepSeek 兼容 Provider；真实模型输出仍需 Schema、Evidence 和人工审核。

## 本次推送范围

本次 GitHub 分支只包含源码、测试、迁移、文档和部署示例，不包含 `data/` 下任何模拟或真实资料。模拟和真实验收资料保留在本机，避免数据授权与公开仓库范围混淆。

## 不进入 Git 的本地或内部资料

- `.env`、任何密钥、数据库、WAL/SHM、数据库备份、`data/uploads/`、虚拟环境和缓存。
- `data/` 下所有模拟夹具、真实资料、真实模型响应和来源文件。
- `docs/product_validation/`：包含评审输入、模型输出和产品验证运行数据。

## 本地启动

```powershell
Copy-Item .env.example .env
# 在本机 .env 或部署 Secret 中填写 MODEL_API_KEY、MODEL_NAME、MODEL_BASE_URL
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/migrate_db.py
streamlit run app.py
```

真实密钥只保存在本地 `.env` 或云平台 Secret，不要提交到 GitHub。首次部署应使用空业务数据库并按部署手册迁移；不要上传开发机 SQLite 数据库。

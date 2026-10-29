# TradeLoop 第三方组件声明

本清单根据 `requirements.txt` 的直接依赖和当前本地环境生成，用于说明组件用途。正式提交前应再次以锁定依赖、发行包元数据和对应官方许可证文件复核；本文件不替代各组件原始许可证。

| 组件 | 项目版本范围 | 当前验证版本 | 用途 | 许可证或来源 |
|---|---:|---:|---|---|
| Streamlit | `>=1.40,<2` | 1.66.1 | Web 页面、交互组件和多页面应用 | Apache-2.0；https://streamlit.io |
| SQLAlchemy | `>=2.0,<3` | 2.1.6 | SQLite ORM、事务和查询 | MIT；https://www.sqlalchemy.org |
| Pydantic | `>=2.8,<3` | 2.14.1 | 输入、模型输出和业务 Schema 校验 | MIT；https://github.com/pydantic/pydantic |
| pandas | `>=2.2,<3` | 2.3.3 | CSV 读取、字段校验和确定性统计 | BSD-3-Clause；https://pandas.pydata.org |
| python-dotenv | `>=1.0,<2` | 1.2.4 | 从本机 `.env` 加载配置 | BSD-3-Clause；https://github.com/theskumar/python-dotenv |
| pytest | `>=8,<10` | 9.1.1 | 自动化测试 | MIT；https://docs.pytest.org |
| Ruff | `>=0.9,<1` | 0.17.2 | Python 静态检查和格式规范 | MIT；https://docs.astral.sh/ruff |

## 使用边界

- 项目未将第三方组件源代码复制进仓库。
- `.venv`、下载缓存和本机安装包不得提交到 Git。
- 间接依赖及其许可证应在最终构建环境中通过包元数据或软件物料清单工具再次导出。
- 外部模型 API 尚未配置；最终若接入，应补充提供商名称、SDK、服务条款、数据处理边界和调用地区。
- 海报、字体、图标、图片或其他素材若来自第三方，必须在最终提交前补充来源和授权状态。

## 最终复核命令

```powershell
pip freeze
python -c "from importlib.metadata import metadata; print(metadata('streamlit').get('License-Expression'))"
```

最终提交人应确认表中版本与实际演示环境一致，并保留必要的许可证文本或链接。

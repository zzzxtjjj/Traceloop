# 设置与评价页面调整

2026-10-31：保留原有品牌样式，新增 `pages/06_设置.py`。

- 差评页移除 API 配置指标；运行编号、模型和 Prompt 仅在“分析记录”中查看。
- 问题列表用中文审核状态和普通说明，取消英文状态大号卡片。
- 设置提供 DeepSeek、百炼、火山方舟、Kimi、智谱及自定义兼容服务。模型和地址以各账户控制台为准；只有 DeepSeek 有此前真实连接证据，其他选项不代表已通过真实兼容性测试。
- 设置使用 JSON Object 请求，附带 Schema，并继续本地验证。服务商不支持该协议时会失败，不自动绕过验证。
- 每次应用服务配置都必须提供对应密钥；当前浏览器会话内生效，不写入 `.env`，不共享给其他会话。清除配置后恢复本机环境参数。关闭或断开会话可能丢失偏好，尚非跨设备账号设置。
- 界面语言为简体中文、English、Deutsch。设置、导航和常用业务操作使用翻译词典；尚未收录的提示回退中文。评价原文、输入和已保存业务内容保持原语言。界面语言与生成内容的目标市场是独立选择。
- 设置页不自动发起真实 API 请求；下次点击业务分析才使用当前配置。

主要模块：`services/app_preferences.py`、`core/display_language.py`。测试覆盖配置隔离、地址检查、设置应用、语言切换和清除；页面冒烟测试包含新设置页。

参考接口说明：
- https://api-docs.deepseek.com/guides/json_mode/
- https://docs.bailian.console.aliyun.com/zh/model-studio/what-is-model-studio
- https://console.volcengine.com/ark/region%3Acn-beijing/docs/text-generation

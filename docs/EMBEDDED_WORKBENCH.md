# 嵌入式工作台、LiteLLM 与工具链配置

当前操作入口和准确部署说明已经统一到 [联调前检查与部署](INTEGRATION_ACCEPTANCE.md)。

页面使用容器可用高度，项目/消息/配置清单各自滚动；规格、运行与日志使用抽屉。供应商条目支持长名称和窄屏，保持 FastapiAdmin 登录、响应、路由和 Element Plus 风格。

模型 SDK profile、独立 LiteLLM Proxy 与个人 ChatGPT/Codex 授权不是同一配置。普通 API/云凭据可导出环境变量引用；个人订阅不导出共享网关授权。

工具设置加密存储。恢复默认入口已禁用以避免旧实现的版本回退；正常编辑/保存可用。自定义模型 origin 白名单在 `.env` 由管理员设置。Coder API、浏览器、Agent 和源码下载地址分别配置，不能混用 localhost。

请以当前提交的 CI 报告为准。真实账号、外部 Cube/KVM、MCP 网络与 Coder provisioner 仍需部署环境联调。

# ChatGPT / Codex 登录和工具控制台

## 账号登录

在模型页保存 ChatGPT / Codex 配置后，或点击“网页登录”，浏览器会在点击事件中直接打开 **https://auth.openai.com/codex/device**，平台同时取得设备码。只在官方页面登录、输入平台显示的设备码并确认。若浏览器拦截弹窗，点击对话框内“打开官方登录页面”。某些账号需要先在 ChatGPT 设置 → 安全中开启设备码授权。

这是 OpenAI 官方设备授权流程，不是跳到 codex 首页就自动获得令牌。没有共享服务器 Codex 登录文件，也不要求输入 OpenAI 密码到本平台。完成后自动轮询，关闭弹窗不会启动新的授权。网络错误在对话框内显示，可点击“重试授权检查”；“重新授权”才明确申请新设备码。不要把设备码、令牌或 auth.json 发到聊天和日志里。

设备码申请成功只证明授权端点可达，不能替代用户完成登录、订阅权限和真实模型调用验收。

## 启动可选控制台（保留现有配置与数据）

在部署机器的项目根目录运行；Windows 建议使用 WSL：

```bash
python3 scripts/setup_toolchain.py
# 只为缺少/空白项补安全地址；不创建模型密钥、Cube 模板或 Coder 令牌。
docker compose -f compose.yaml -f compose.tools.yaml --profile ai --profile tools --profile architecture up -d litellm coder structurizr
python3 scripts/check_tool_consoles.py
```

不要使用 `down -v` 或 `--fresh` 升级。首次启动 LiteLLM 会迁移它自己的数据库，需等待完成。

| 工具 | 本机浏览器入口 | 登录/范围 |
|---|---|---|
| FastapiAdmin | http://localhost:8000/api/v1/web/ | 原有平台账号 |
| Temporal | http://localhost:8233 | 当前开发环境控制台 |
| LiteLLM Proxy | http://localhost:4000/ui/ | UI_USERNAME 默认 admin；密码使用部署端 .env 的 LITELLM_UI_PASSWORD，未单独配置则是 LITELLM_MASTER_KEY；不要公开这些值 |
| Coder | http://localhost:7080 | 首次由你创建 Coder 管理员；和 FastapiAdmin 不是同一登录态。控制台可用不代表 provisioner/模板已配置 |
| Structurizr Local | http://localhost:8080 | 查看 architecture/workspace.dsl；此开发服务仅绑定本机 |
| LangGraph、OpenSpec、diagrams | 无独立后台 | 镜像内的库/CLI，在工作台运行详情查看产物 |
| ToolHive、Serena | 外部 MCP/CLI，不是本平台网页登录后台 | 需部署受控 MCP，见 integrations/toolhive/README.md；MCP API URL 不等于网页 |
| CubeSandbox | 需实际集群/模板/API 授权 | 不能在普通容器中伪造 KVM 集群或模板；见 integrations/cube/README.md |

浏览器 URL 使用 localhost，容器内部的服务 URL 使用 litellm:4000、coder:7080、structurizr:8080 等 Compose DNS 名称；不要混用。若从另一台电脑访问，localhost 指向那台电脑，需要管理员配置受控反向代理和浏览器入口；不要直接把无认证控制台暴露到公网。

“配置存在”“控制台 HTTP 可达”“模型/工作区实际执行”是三个不同状态。LiteLLM/Structurizr 探针检查实际 HTTP 服务，而不再仅凭安装了 SDK/Docker CLI 就显示成功。

# 嵌入式工作台、LiteLLM 与工具链配置

## 页面变化

`/factory` 不再叠加大幅 hero/统计卡片到 FastapiAdmin。页面按 `visualViewport` 和容器真实 top 测量剩余高度，聊天消息/项目列表自己滚动；输入框和发送/启动按钮固定在可见区域。运行图、规格、日志移到抽屉。窄屏项目列表改为折叠入口，不强行排三列。

`/factory-providers` 改为紧凑条目，供应商名称/模型名允许截断或换行，操作区可换行，不挤出卡片。选择供应商、认证方式、模型、Base URL 与 LiteLLM 参数放在同一个抽屉里。保留当前 catalog 全部供应商、实时模型发现和自定义兼容供应商，不把支持范围缩回少数几个演示项。

`/factory-toolchain` 每张卡都有“配置”和文档入口。配置抽屉包括原生 SDK/CLI 组件的有效参数、状态来源和部署动作；需要其他服务时给出对应服务页面链接。配置存在仍不等于已部署成功。

## OpenAI API 与 ChatGPT/Codex 账号是两种认证

- `OpenAI`：API 平台密钥，API 用量计费。
- `ChatGPT / Codex account`：在页面点击网页登录，后台取得 device code；页面只打开官方 `https://auth.openai.com/codex/device`。用户自己在官方页面输入一次性代码、登录并授权，不把账号密码交给本平台。

这是 LiteLLM 的 `chatgpt/` 订阅路由与 Codex device authorization，不是把 ChatGPT 登录 cookie 伪装成 OpenAI API Key。可用模型、设备授权开关与额度取决于账号/组织策略。必须在账号安全设置允许 device-code 登录；授权失败不会降级使用另一个用户或服务器上的凭据。

每个 profile 的待授权状态和 tokens 加密保存。完成/过期/取消后清理设备代码。后端轮询间隔受限制，敏感返回均 `Cache-Control: no-store`；只有 profile 所属用户能读取状态或轮询。

LiteLLM 当前原生 ChatGPT 适配器使用进程级 token 文件，不直接适合多个用户。此实现将每次订阅调用放入隔离子进程，使用独立临时 0700 目录和 0600 auth 文件，不给其他 profile 复用，也不修改 API/worker 全局环境变量。只继承 PATH/LANG/模型配置，平台数据库/管理密钥不会传入。刷新后的 token 只写回同一账号版本，断开授权或删除 profile 后不能被旧请求重新绑定。

没有在仓库保存任何用户模型 API Key、ChatGPT 登录 token 或 device code。实际网页授权只能由用户自己完成；CI 使用协议夹具，不声明真实账号已授权。

## LiteLLM 参数与配置文件

每个 profile 可配置 timeout、有限 retries、top_p、seed、reasoning_effort。原字段 temperature/max_tokens 保留。AWS/Vertex 等额外字段只开放有类型的白名单，不允许 arbitrary headers、callbacks、代理地址、`extra_body` 或绕过端点安全策略的 transport 参数。

Bedrock 支持 access key、secret key、session token 与 region；Vertex 支持 service-account JSON、project、location。这些额外凭据加密落库，API 只返回已配置的字段名。字段留空保留原值；普通 API Key 行为不变。ChatGPT 不允许同时填写 API Key/Base URL。

“导出 LiteLLM YAML”输出 `model_list`、`litellm_params` 和 `litellm_settings`。任何敏感项都输出 `os.environ/LITELLM_PROFILE_...` 引用及环境变量名，绝不把真实密钥打进下载文件。导出后运行独立 LiteLLM Proxy 时，仍需在其环境设置这些变量。ChatGPT profile 不导出为共享 token 目录，防止破坏账号隔离；页面明确列出跳过项。

Base URL 继续使用管理员 origin 白名单。普通用户不能在供应商页面随意把请求发往内网管理接口；管理员在工具链的 LiteLLM 设置中批准所需 origin 后生效。SDK 详细日志仍被凭据隐私策略覆盖。

## 工具链可配置项与生效

`ToolSettingsService` 使用加密的全局配置记录，仅 FastapiAdmin 超级管理员可读/写配置详情；普通用户仍可看非敏感组件状态。每个工具都有一个受约束的字段集合，不允许从前端修改整个 settings、任意文件路径或任意命令。

OpenSpec、diagrams、LangGraph、Temporal、Structurizr、LiteLLM、ToolHive/Serena、Cube 与 Coder 均有配置入口。Model API 由用户自己配；服务 token 由管理员在页面填写。OpenSpec/diagrams 仅允许开启要求，不提供“关闭质量门禁”的快捷开关；LangGraph 维持受控的两次 schema 尝试。

保存后 API 与 worker 的每次工具活动重新加载有效配置。Temporal address/namespace/task queue 是长连接，必须重启 API/worker；返回信息明确提示。其他服务地址、凭据与工具选项用于下一次相应活动，不是假保存。

源环境变量仍作为默认值，未配置的字段不覆盖它们。恢复默认只删除这个工具对应的配置项。浏览器列表、日志和响应不返回 token 明文；编辑留空表示保留密钥。

## 本地准备（无模型密钥、无破坏已有数据）

```powershell
python scripts/init_env.py
python scripts/setup_toolchain.py

docker compose -f compose.yaml -f compose.tools.yaml --profile tools up --build -d
```

`setup_toolchain.py` 只给缺失/空值补 Coder 与平台互通默认地址，绝不覆盖非空配置。Compose tools 为 Structurizr 本地查看服务和 Coder 添加 loopback 端口；不挂载 Docker socket，不自动打开公网。Coder `latest` 只作为 opt-in 引导镜像，部署前请选择已验证 digest；不要把它当成已锁版本的生产构建。

然后在工具链页面：

1. Coder 首次管理员登录、部署 `integrations/coder` 模板，填写模板 ID、服务 token 和授权 owner ID；将 Coder 服务页面填为 `http://localhost:7080`。私有网络 URL `http://coder:7080` 给后台用，不是浏览器 URL。
2. ToolHive/Serena 按卡片里的脚本准备和启动，填写代理端点。工具本身是独立 MCP 运行时，不冒充 LiteLLM 提供商。
3. Cube 必须部署真实 Cube/KVM 环境并导入全栈模板；页面填写端点/模板/key。一般 Docker Compose 不能自动替你生成可用 Cube 模板。
4. Structurizr DSL 预览服务默认 `http://localhost:8081`；parser 验证仍需要原受控执行配置。`compose.sandbox.yaml` 是管理员 opt-in 高权限方案，与只读查看服务不同。
5. 模型供应商页面配置你的 API Key 或在官方网页完成 ChatGPT 授权。

## 验证范围

回归覆盖：加密设置生效/恢复、非管理员拒绝、额外凭据/模型参数白名单、YAML 不含密钥、账号授权 pending/成功/跨用户/取消、兼容 demo 路径。

前端仍完整 Vite 构建后执行 vue-tsc，不降低 strict。CI 增加已登录态 API 夹具的浏览器布局检查（1366×768、1280×720、820×760、390×780），分别检查三个嵌入页无横向溢出、主要操作在视口内，并保留截图。该浏览器测试覆盖真实构建的 Vue/Element Plus 页面，但不是实际付费模型或外部 Cube/Coder/Serena 联调；真实核心 API/Temporal/数据库流程仍由 core-stack 验证。

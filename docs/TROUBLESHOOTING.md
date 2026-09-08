# 故障排查：先定位哪一段失败

## 构建前的问题

**docker: command not found / daemon 无法连接。** 检查 Docker Desktop 是否运行、WSL Integration 是否启用，执行 `docker version`。不要同时安装两套守护进程后混用 socket。

**git fetch 下载失败。** 检查 DNS、代理、证书、GitHub 访问与固定 SHA 是否可取。初始包不包含整个上游，网络是必要条件。不要私自改 master 以绕过失败，否则失去版本与 overlay 兼容保证。

**uv 解析冲突或 package not found。** 看具体依赖名称和索引。联合环境会保留上游 pin；不得无证据把上游版本降级。查看 `runtime/combined/pyproject.toml`，按官方仓库确认该提交是否要求特定索引/平台。网络镜像缺包和真实依赖冲突不是同一问题。

**pnpm lock 不匹配或 vue-tsc 失败。** 保留错误文件名，先检查 Node22、pnpm9.15.3 和下载的固定上游是否一致，再区分原上游代码还是 overlay 的 TypeScript 错误。不得删除 vue-tsc 命令来假装构建成功。overlay 在本次环境只做了 TypeScript 语法转译检查，没有运行完整 Vue 编译器。

## 启动的问题

**init-data 或 migrate exited。** exited(0) 是一次性成功；非零才是失败。查看对应日志。权限问题检查 Linux data 目录归属及是否位于支持相应权限的文件系统，不对整个主机目录递归 chmod777。

**PostgreSQL password authentication failed。** 首次初始化后，容器环境变量改变不会自动修改已有卷中的数据库密码。恢复原 `.env` 或用数据库管理方式更改密码；不要为了修配置立即删卷。

**端口被占用。** 修改 Compose 左侧主机端口，例如 `127.0.0.1:8002:8000`，容器之间仍访问 api:8000。产品默认8010、平台8000，不要改错右侧或服务名。

**登录页空白/脚本404。** 检查前端 build base 为 `/web/`、dist 已复制到 backend/dist，并访问 `/web/` 而不是服务根 `/`。源码中的独立新增路由是 `/web/#/factory`，产品是 `/web/#/business`。

**登录成功但新增页401。** 检查 Auth.getAccessToken、原会话是否已过期、Redis 是否同一实例、SECRET_KEY 是否改变。不要给新增接口去掉鉴权。诊断 API 的 FACTORY_TOKEN 与上游登录 token 不能混用。

## 工作流的问题

**一直 QUEUED。** 依次查看 worker 日志、Temporal健康、任务队列名、namespace、outbox attempt/error。API health 只证明API+DB。必要时运行 `docker compose exec worker python scripts/probe_integrations.py temporal`，连接通过仍不等于对应队列有 worker。

**一直 AWAITING_APPROVAL。** 这是等待人工确认，不是卡死。审批 hash 必须匹配当前 run；未支持项需明确接受。错身份、过期页面或重复不一致决定会被拒绝。

**GENERATING 失败。** 检查固定模板 receipt、上游 contract、Graphviz、diagrams、磁盘空间与目录权限。不要将 `.factory-upstream.json` 手工写成目标SHA来绕过校验。

**OpenSpec 验证失败。** 默认是严格门禁，读取具体 change、requirement 和 scenario 错误。修改 generator 的文档模板并补测试，不在 UI 中将 failures 强制改passed。独立命令：

```bash
# 在对应 product 目录中：
openspec validate create-product --type change --strict --no-interactive
```

**下载409。** 可能尚未READY，或ZIP发生了篡改/损坏。检查状态和哈希，重新生成新的run，不修改数据库中的SHA去掩盖不同文件。

## 模型与外部工具的问题

**LiteLLM401。** 区分平台到网关 key 和网关到模型 provider key。configure_model 只设置本地Ollama路径，不代表商业API密钥已配置。

**LiteLLM400 / JSON格式不支持。** 检查模型是否支持请求中的 response_format、max_tokens 等。先用模型官方接口验证能力。必要时在 provider adapter 中做显式能力映射，并增加测试，不能默默 drop 所有未知参数后忽略行为变化。

**模型总是输出设备维修。** 检查provider是否仍为demo。demo是固定测试fixture，必须改为litellm且探针通过才会分析真实需求。

**Serena连接不上。** 检查streamable HTTP `/mcp`、ToolHiveproxyport、worker到主机的网络、token、项目索引、Python语言服务器。只用curl收到某个HTTP状态不足以验证MCP initialize/session/tool call。

**Cube连接localhost:3000失败。** worker容器的localhost不是你的LinuxCube节点。填真实私网API地址；检查控制面与数据面各自能否到达、证书及templateid。

**Coder创建成功但IDE不能打开。** POST接受不等于provisioner构建成功。查看Coderbuild日志、template、agent连接与持久卷。源码导入目前是手工步骤，不会自动出现在新IDE中。

## 求助时提供什么

提供失败阶段、命令、退出码、去密后的最后几十行日志、操作系统、固定模板SHA、所用image tag/digest和复现步骤。不要上传整份.env、access_token、完整数据库或未脱敏需求。优先让AI依据具体文件和测试修复，而不是“全部重写成更简单的版本”。

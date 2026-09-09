# PR #4 最后约束与验收

本次不合并主分支、不清空数据库、不修改已有 `.env`。保留 `/factory-api` 兼容接口，但新工作台继续使用 FastapiAdmin 原生认证、响应格式和操作日志表。

## 1. 需求与 AI 分析必须是同一版本

AI 请求发出前读取对话哈希；保存时在数据库事务、项目行锁下核对哈希。用户在分析过程中补充需求，旧分析保存返回 HTTP 409，不能覆盖新回答。

AI 分析 JSON 持久化 `conversation_revision`，与保存后的对话绑定。历史 READY 数据若没有版本凭证，必须重新澄清，不能直接生成。无需删表或破坏性迁移。

新版启动请求必须带 `expected_revision`。页面、命令行验收脚本都提交当前审阅的版本。遗漏返回 428；旧页面持有的哈希与当前版本不符返回 409。即使另一页面已把新需求分析成 READY，旧页面也不能误启动。相同幂等请求仍返回原 Run，不重复派发。

Run 冻结当时的需求、分析、验收条件和版本。项目后续修改不改写历史 Run；审批仍针对该 Run 的 `spec_digest`，不是自动批准最新需求。

## 2. 凭据不能进入操作日志或 SDK 日志

`factory/privacy.py` 对研发路由继承原 `OperationLogRoute`，使用原操作日志字段和数据库 writer，但不调用其请求体/响应体收集器。记录账号、路径、方法、状态、耗时和摘要，统一省略正文；不修改实际传给控制器的请求。

校验失败（含 JSON 损坏、未知字段）返回固定说明，不回显 Pydantic 的原始 input。未知异常不输出 SDK 异常链或局部变量。原响应的 BackgroundTask 会被保留，不因审计覆盖。

在标准日志记录生成阶段省略 LiteLLM/OpenAI/Anthropic/HTTP/MCP/Cube SDK 的消息、参数、异常和堆栈，覆盖后续创建的非传播 logger；LiteLLM 同时禁用详细调试和消息记录。宿主日志保留原文件、轮转与关联 ID，但即使 dev 环境也禁用 Loguru `diagnose`/`backtrace`。

这些措施不代替部署边界：反向代理、外部模型网关、APM/数据库管理员的日志策略仍需独立配置。不要开启代理请求正文记录；不要把密钥写入模型名称、URL 路径或项目需求。

## 3. 完整模式必须有实际验收回执

`factory/evidence.py` 集中执行失败即阻断的条件。以下任何一项缺失、失败、跳过或哈希不匹配，都不能成为 READY：

- 实际 ToolHive/Serena 上下文，OpenSpec 分析与交付校验成功。
- Structurizr parser 通过、交付 DSL 与验证源一致、diagrams 实际生成便携 SVG。
- Cube 沙箱执行固定全栈验收：前端 Vite 构建、vue-tsc 类型检查、独立 PostgreSQL/Redis、原生 FastapiAdmin 登录、用户数据隔离、未登录访问/伪造 owner/跨用户关联拒绝。
- Cube 回执的输入 ZIP SHA-256 与上传字节一致。只有 `source_only` 回执不能完成完整模式。
- 源码在验证和打包之间不能改变；最终 ZIP 在宣布 READY 前重新核对哈希。
- Coder 工作区运行中、Agent 已连接，返回与最终 ZIP 相同的导入 SHA-256；仅创建工作区不算完成。

基础模式仍可只执行静态/契约测试，明确标记 `full_stack=not_run`。完整模式通过后质量为 `generated_crud_stack_verified`。这只覆盖现有生成器的 CRUD/关联能力，不代表任意业务需求已实现；浏览器交互、人工业务验收、生产安全审计仍单列，`production_ready=false` 不会自动变成 true。

## 4. 构建离线全栈验收模板

先在仓库根目录构建三个镜像（与该提交保持一致）：

```powershell
docker build --target frontend -t ai-rnd-frontend-smoke .
docker build -t ai-rnd-foundation:0.1.0 .
docker build -f Dockerfile.acceptance -t ai-rnd-acceptance:ci .
docker build -f integrations/cube/Dockerfile.fullstack -t ai-rnd-cube-fullstack:0.2.0 .
```

最后一个镜像以官方 `ghcr.io/tencentcloud/cubesandbox-base:2026.16` 为底座，保留其 envd/入口。依赖在构建阶段安装并冻结；运行时不执行 npm/uv 安装。镜像中有固定 `/opt/rnd-verifier/full_stack.py`、Python 环境、与产品锁文件匹配的前端缓存、PostgreSQL 和 Redis。基座标签不是不可变 digest；对外部署应在验证后固定你实际使用的 digest。

按你部署版本的 Cube 镜像导入/模板创建流程注册镜像，并给模板至少 6 GiB 内存；把得到的模板 ID 配置为 `FACTORY_CUBE_TEMPLATE`。源检查用的 `Dockerfile.verifier` 不是全栈模板。代理协议/证书、Cube 集群地址、配额和模板启动仍须在你的真实 Cube 环境验证。

SDK 使用 `user="factory"` 运行固定命令，禁用互联网访问。验收器在私有临时目录创建一次性 PostgreSQL/Redis，绑定随机 loopback 端口，生成自己的会话密码；不继承平台 JWT、模型 API Key 或平台数据库连接。退出时关闭服务并清理目录。PostgreSQL 的 trust 认证仅存在于这个一次性、仅 loopback 的验收集群，不用于产品部署。

## 5. 验证与升级

GitHub Actions 的 `core-stack` 会完成真实平台认证、需求澄清门禁、Temporal 派发、OpenSpec/架构/生成/审批/ZIP，再用与 Cube 相同的固定验收器，在一次性 CI 容器内启动产品全栈。模型 HTTP 响应是明确标识的测试夹具，不是实际付费模型。额外检查真实 FastapiAdmin 操作日志表是否泄漏测试凭据。

CI 仅复制 `data/ci-reports` 到单独报告目录，不放宽整个 `data/` 权限，也不上传 `.env`。报告包括 `credential-audit.json`、`platform-run.json`、`product-stack.json`、`coverage.json`。

真实外部工具联调入口：

```powershell
# FACTORY_USER_JWT 在本地设置为你自己的登录凭证，不要提交到 GitHub。
uv run python scripts/smoke_workbench.py --provider-id YOUR_PROVIDER_ID --requirement requirement.txt --full --approve --accept-limitations
```

仅在你确实接受本次规格和未支持项时使用这两个审批参数。否则在网页里审阅后批准。脚本会要求真正回答澄清问题，核对全栈/Coder/ZIP 回执并保存实际证据；不会伪造在线验收结果。

升级前备份 `.env`、`data/`、数据库。重建 API 与 worker；旧 READY 项目先重新澄清。已有运行冻结旧需求，不会改为新需求；跨版本恢复的旧验证结果若没有源码摘要，必须重新验收/创建新 Run，不能用旧结果冒充新门禁通过。不要对真实部署执行 `docker compose down -v`。

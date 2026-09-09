# FastapiAdmin AI 研发工作台 0.2：更新、配置与验收

本次升级延续 PR #4：真正复用固定提交 FastapiAdmin 的管理布局、登录、会话、Element Plus、HTTP 拦截器与统一响应，不用一个独立 HTML 演示页冒充管理平台。

**能力边界：当前生成器实现有类型的 CRUD、用户归属隔离和无环父子关联。** 审批流、支付、实时采集等不能实现的业务必须出现在未支持项，由用户明确接受。完整“工具链流程”不等于所有任意业务、浏览器交互或生产安全均已验收。

## 一、更新与入口

先备份数据库、`data/` 和 `.env`，保存到仓库外；不要执行 `docker compose down -v` 清除你的真实数据。PR 尚未合并时，拉取分支而不是只拉 main：

```bash
git fetch origin
git switch feat/fastapiadmin-ai-rnd-workbench
git pull --ff-only
python3 scripts/init_env.py
docker compose up --build -d
```

初始化脚本只追加缺失的新配置，不覆盖已有密码/模型设置。迁移服务应用 `rnd_0002`，增加供应商、澄清状态和执行阶段；老项目不删除，新增运行必须重新走澄清门禁。已有 Temporal v0.1 运行通过版本补丁保留原命令序列和审批等待流程。

```bash
docker compose ps -a
docker compose logs --tail=100 migrate api worker temporal
```

浏览器打开 `http://localhost:8000/api/v1/web/#/factory`，先用 FastapiAdmin 登录。三个原生菜单是：研发工作台、模型供应商、研发工具链，路由分别为 `/factory`、`/factory-providers`、`/factory-toolchain`。

原有本地源码启动方式仍需重新 `bootstrap`、构建前端并应用迁移。不要修改生成的 `runtime/FastapiAdmin` 后期望它覆盖 overlays；重新 assemble 会覆盖 runtime。对 runtime 有本地修改时先另行保存，勿直接执行 `--replace-runtime`。

## 二、原生代码分层

```text
factory/host.py                          FastapiAdmin 应用工厂、AuthPermission、原生响应/审计路由
factory/modules/workbench/controller.py  HTTP 路由、输入、响应
factory/modules/workbench/service.py     澄清编排、供应商探针、产物读取策略
factory/modules/workbench/crud.py        owner 过滤、事务、版本检查、Run/Outbox
factory/modules/workbench/schema.py      Pydantic 请求契约
factory/modules/workbench/model.py       共享 ORM 模型导出
factory/database.py                     控制平面唯一 SQLAlchemy metadata
factory/api.py / repository.py          旧导入路径兼容层
factory/providers/                      LiteLLM、MCP、Cube、Coder 适配器
factory/activities.py / workflows.py     Temporal 活动与确定性工作流

overlays/platform/api/index.ts          安装为 src/api/module_factory/index.ts
  FactoryConsole.vue                    项目/对话/门禁/规格表格/架构预览/流水线
  ProviderManager.vue                   模型配置卡片与抽屉
  ToolchainCenter.vue                   组件职责、配置和运行范围
```

Worker 不加载整个 FastapiAdmin Web 应用，所以领域模型/服务保留在独立 factory 包，而不是复制两套 ORM。生产入口明确注入 FastapiAdmin 的 `SuccessResponse`、`OperationLogRoute` 和 `AuthPermission`；测试/诊断入口单独注入身份，不能用于生产登录。

标准 API 为 `/api/v1/factory/*`，业务成功码与 FastapiAdmin 一致为 `0`，创建/排队保留 HTTP 201/202，日期可序列化。旧 `/factory-api/*` 保留原始 JSON 兼容格式，不依赖请求 URL 是否带 `/api/v1` 来猜测响应结构。

首次用超级管理员验收。普通角色需要在 FastapiAdmin 菜单/权限管理中增加并授予功能权限 `module_factory:workbench:query`，重新登录；不能靠前端隐藏代替后端授权。mixed-mode 已内置三条菜单路由，不要重复创建相同路径。

## 三、先配置模型，再分析需求

在“模型供应商”新增配置。支持 OpenAI、Anthropic、Azure OpenAI、Gemini、DeepSeek、Groq、OpenRouter、Ollama、Mistral、xAI、LiteLLM Proxy 和自定义 OpenAI-compatible。

填写真实模型 ID、API Key、可选 Base URL、Temperature、Max Tokens。Azure 另外填写 API Version 和部署名。OpenRouter 的 `anthropic/…` 等原生模型 ID 会保留，由 LiteLLM 添加外层供应商路由前缀。自定义 API 的带 `/` 模型名不会误切换到另一个供应商。

OpenAI/Anthropic 等直连通过 **LiteLLM SDK**，不必另外启动 LiteLLM Proxy 容器；需要统一网关时选择 LiteLLM Proxy 配置。连接测试确实发送模型请求，可能产生费用，必须收到符合要求的 JSON 响应才成功。未知、禁用或别人的 provider ID 返回错误，绝不偷偷退回系统模型或固定 Demo。

### 密钥和自定义地址

API Key 使用 `FACTORY_CREDENTIAL_ENCRYPTION_KEY` 派生的 Fernet 密钥加密存入 PostgreSQL。API 只返回 `has_api_key`，不回显明文；更新时空输入保留原值，关闭编辑抽屉会清空内存中的输入。密钥不进入 Run、LangGraph 状态、Temporal 参数或源码包。不要丢失/随意更换加密主密钥。

自定义、Ollama 和代理地址必须先获得管理员批准。例：

```dotenv
FACTORY_MODEL_ALLOWED_ORIGINS=["http://litellm:4000","http://host.docker.internal:11434","https://models.example.com"]
```

这里填 origin，不含 `/v1`；页面 Base URL 可以包含供应商要求的路径。端口是 origin 的一部分。默认生成配置仅批准本地 LiteLLM 与 Docker Desktop 宿主 Ollama。修改后重建/重启 API、worker。该白名单不替代生产环境的出口防火墙，也不是 DNS 重绑定防护承诺。不要允许云元数据地址或任意内网管理端点。

## 四、严谨的对话门禁

创建项目后先真实调用模型分析，首次分析必须向用户确认范围；即便模型第一次直接说 ready，平台也会要求至少一次用户回答。

多轮模型输入包括原始需求、历史提问、用户回答、验收标准和上一轮分析。`ready=true` 必须没有阻塞问题且有验收条件；`ready=false` 必须提问。最多两次结构化输出尝试，不进行无限收费重试。

AI 调用期间新回答到达，旧分析结果不能覆盖它：服务保存时核对 conversation revision，冲突返回 409。补充回答使需求失效，重新分析后才能启动下一次运行。Run 冻结需求快照、验收标准和规格摘要，不随后续对话改变。

页面的模型请求超时与实际推理时间匹配，KeepAlive 切页会停止轮询，返回后恢复；网络断开显示提示而不是伪装正常运行。人工审阅提供业务实体/字段表、验收标准、未支持项及实际生成的 OpenSpec、DSL、ER SVG、部署 SVG；JSON 只放在开发者折叠区。

## 五、每个组件实际用在哪里

| 组件 | 实际调用/作用 | 本次运行证据 |
|---|---|---|
| FastapiAdmin | 原生用户、角色、会话、UI、响应；固定版本生成模板 | 原生接口、模板 manifest |
| LiteLLM | 选中供应商的真实 SDK 调用，需求澄清与规划 | provider ID、失败/成功阶段；不记录 Key |
| LangGraph | 澄清图、结构化规划/校验图 | 分析结果、Pydantic 规格 |
| Temporal | 持久化状态、Outbox、重试、人工 signal | workflow、stage_details、Event |
| ToolHive | 部署并代理只读 Serena MCP，限制可见工具 | 管理员部署与代理配置；请求从该端点执行 |
| Serena | MCP initialize/list_tools、读取固定模板多个 Python 文件的符号 | context Activity 的 used/工具回执 |
| OpenSpec | 提案、设计、任务、需求和规格；执行 strict validate | CLI exit code 与实际文件 |
| Structurizr DSL + C4 | C1/C2/C3 DSL；完整模式调用真正 parser | parser_validated 与镜像/输出回执 |
| diagrams | 生成部署 SVG 和 Python 源；内嵌可信 PNG 资源 | 可移植 SVG；不依赖 worker 绝对路径 |
| CubeSandbox | 上传本次受信任源码，创建沙箱、执行固定检查、销毁 | sandbox ID、检查结果、生命周期 |
| Coder | 打包后创建/复用工作区，自动下载本次 ZIP、验 SHA | running、connected、源码 SHA 元数据 |

完整顺序：

```text
输入 → AI 澄清/提问 → 用户回答 → READY
→ ToolHive/Serena 上下文 → LangGraph/LiteLLM 规格规划
→ OpenSpec + C4/ER/部署图 → 人工审阅并批准精确 digest
→ FastapiAdmin 产品生成 → Cube 检查 → 排除敏感文件并打包
→ Coder 自动导入并核对 SHA → 本次运行完成
```

审批前的 OpenSpec 任务不能提前勾选为已开发。交付包携带澄清要求；若标记 C4 parser 已通过，交付 DSL 必须与实际验证的 DSL 字节一致。

### 工具配置顺序

先让基础模式完成供应商、澄清、Temporal、生成和下载。然后：

1. 按 `integrations/toolhive/README.md` 执行准备、部署和 Serena 探针。索引限定 Python 模板，不要求未安装的 TypeScript LSP。只暴露读取工具，不挂载 `.env`、用户 Home 或 Docker socket。
2. 配置 `FACTORY_CUBE_API_URL / FACTORY_CUBE_API_KEY / FACTORY_CUBE_TEMPLATE`，确保该模板与 SDK、Python 固定检查命令兼容。按 `integrations/cube` 原有说明部署；不要把 E2B 公有服务默认为 Cube。
3. 按 `integrations/coder/README.md` 部署本次新增的自动导入模板，设置 Coder URL/Token/Template/Owner、`FACTORY_CODER_AUTO_IMPORT=True` 和工作区可访问的 `FACTORY_CODER_FACTORY_URL`。
4. 完整模式的 Structurizr parser 当前通过 Docker 执行，需要固定镜像和正确的宿主 `data` 路径。仅在受信任本机开发环境使用：

```bash
docker pull structurizr/structurizr:2026.06.28-noble
docker compose -f compose.yaml -f compose.sandbox.yaml up --build -d
```

此 override 给 worker Docker socket 权限，等价于高权限主机控制，不适合公网/不可信多租户。生产应独立隔离解析/执行服务。Windows 用户填写实际 WSL Linux 宿主路径，不要给 Docker bind 传容器内 `/app/data` 或 Windows 盘符字符串。

完整模式缺组件直接拒绝；真实调用失败在对应阶段终止，不降级 static 或创建空工作区后继续报成功。基础模式明确记录跳过项，不计为阶段通过。

## 六、验证与证据解释

`configured` 只代表依赖/配置存在，不代表连通。`READY` 代表本次选定流水线结束，不代表 production-ready。**当前 Cube 固定检查为源码检查，不会自动在 Cube 中启动 PostgreSQL/Redis/Vue 完整产品。** 页面和 `quality.json` 保留 `full_stack=not_run` 等未执行项。

本 PR 增加三层自动验证：Python 回归合同、真实 pinned FastapiAdmin 的 Vite/vue-tsc 构建、独立 CI PostgreSQL/Redis/Temporal 栈。后者使用真实 LiteLLM SDK 对接明确标识的 HTTP 模型夹具，实际跑澄清—回答—审批—生成—ZIP，再从 ZIP 构建产品前端，验证真实 FastapiAdmin 登录、Redis 会话和 PostgreSQL 上的业务归属隔离。它不是对真实 AI 输出、Cube、Coder、ToolHive 服务的联调声明。

CI 隔离脚本 `compose.ci.yaml` / `Dockerfile.acceptance` / `scripts/ci_core_e2e.py` **只能用于一次性测试环境，禁止和你的真实部署组合**。`scripts/verify_delivery_stack.py` 仅接受 `rnd_acceptance_*` 测试数据库，关闭验证码只作用于该测试进程，不修改正式配置。它验证 ASGI/API 与前端构建，不冒充浏览器业务验收。

真实完整服务验收可以在页面进行，也可在本地设置 `FACTORY_USER_JWT` 后运行：

```bash
uv run python scripts/smoke_workbench.py \
  --provider-id 你在页面创建的配置ID \
  --requirement requirements.txt --full --approve --accept-limitations
```

脚本会展示并要求回答真实 AI 的澄清问题。`--approve`/`--accept-limitations` 是明确授权；未传时不会偷偷批准。不要把 JWT 放进命令行参数、截图或 Issue。脚本会核对各完整模式回执和下载哈希，保存 `product.zip`、`run-receipt.json`、`events.json`。

不可变源码 ZIP 在 Coder 导入前就已生成。后续 Coder 回执存平台 Run，不回写 ZIP 造成哈希漂移。查看最终运行详情和源码质量报告时，要区分这两个时间点。

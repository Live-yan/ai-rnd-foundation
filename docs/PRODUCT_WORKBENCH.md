# FastapiAdmin AI 研发工作台 0.2

本版本把原来的单页 Factory Console 改造成 FastapiAdmin 原生交互模块，并把模型供应商、需求澄清、工具链状态和 Temporal 运行阶段纳入同一条可观测流水线。

## 1. 页面结构

启动后仍从 FastapiAdmin 登录。研发相关菜单分为三页：

- `/factory`：AI 研发工作台。项目、需求对话、AI 澄清、规格审批、运行阶段、日志、下载和 Coder 入口。
- `/factory-providers`：模型供应商。按当前登录用户保存配置。
- `/factory-toolchain`：工具链中心。展示组件职责、配置状态和完整模式要求。

前端不再直接 `fetch('/factory-api')`，而是在 `frontend/web/src/api/module_factory` 中复用 FastapiAdmin 的 `@utils/request`、Token 拦截器和统一 `ApiResponse` 约定。后端新增 `/factory/*` 标准接口；旧 `/factory-api/*` 保留为兼容别名，便于已有 smoke/tests 平滑迁移。

## 2. 严谨的需求入口

交互流程改为：

```text
用户输入软件需求
  ↓
LangGraph clarification graph
  ↓
LiteLLM → 当前用户选择的真实模型供应商
  ↓
是否仍有阻塞问题？ ── 是 → 回到用户继续回答
  ↓ 否
生成明确理解、假设、风险、验收标准
  ↓
Clarification = READY
  ↓
才允许创建 Temporal 研发 Run
```

`READY` 不是模型随便返回一个布尔值即可。Pydantic 会强制：

1. `ready=true` 时不能还有阻塞问题；
2. `ready=true` 必须有可测试的 acceptance criteria；
3. `ready=false` 至少要提出一个阻塞问题。

交互页面不再用固定设备检修 Demo 假装“AI 已分析”。固定 `demo_spec()` 仅保留给单元测试和旧兼容 API。

## 3. 模型供应商

支持以下配置类型：

- OpenAI
- Anthropic / Claude
- Azure OpenAI
- Google Gemini
- DeepSeek
- Groq
- OpenRouter
- Ollama
- Mistral
- xAI
- LiteLLM Proxy
- 自定义 OpenAI-compatible API

正式流程通过 LiteLLM SDK 统一调用。每个配置包含模型 ID、可选 Base URL、Temperature、Max Tokens 和 API Key。

### 密钥安全

API Key 不写到 Run，不返回给前端，也不明文存 PostgreSQL。平台使用 `FACTORY_CREDENTIAL_ENCRYPTION_KEY` 派生 Fernet 密钥加密保存。更新到本版本后先执行：

```bash
python3 scripts/init_env.py
```

已有 `.env` 不会被覆盖；若缺少新的加密主密钥，只追加该变量。**不要丢失或随意轮换该值，否则旧供应商密钥无法解密。**

供应商“测试连接”会真实请求模型，可能产生少量 API 费用。

## 4. 完整工具链的实际数据流

完整模式的阶段顺序为：

```text
1 Clarify       LangGraph + LiteLLM
2 Context       ToolHive + Serena
3 Plan          LangGraph + LiteLLM + Pydantic
4 OpenSpec      proposal/design/tasks/spec + strict validate
5 Architecture  Structurizr DSL/C4 + Graphviz ER + mingrammer/diagrams
6 Human Gate    Temporal signal
7 Generate      pinned FastapiAdmin golden template + deterministic generator
8 Sandbox       CubeSandbox
9 Package       secret exclusion + manifest + SHA-256 ZIP
10 Coder        create long-lived IDE workspace
11 Complete     Temporal final state
```

### FastapiAdmin

FastapiAdmin 是平台交互、登录鉴权、Vue UI 和默认生成模板，不另造一套管理壳。当前固定上游提交仍由 `templates/fastapiadmin/manifest.json` 管理。

### LangGraph

LangGraph 负责两个短生命周期 Agent 图：需求澄清和结构规划。Temporal 负责长生命周期持久化状态，两者不抢同一份调度职责。

### LiteLLM

LiteLLM 统一模型供应商差异。供应商档案从 PostgreSQL 解析成运行时 Profile 后才交给模型网关，任务记录只保存 provider id，不复制密钥。

### ToolHive + Serena

完整模式要求 `FACTORY_SERENA_URL` 指向 **ToolHive 管理的只读 Serena MCP**。Context Activity 会真实执行 MCP initialize、list tools，并对固定 Golden Template 调用 `get_symbols_overview`，而不是只检查环境变量存在。

按照 `integrations/toolhive/README.md` 先完成部署和探针。不要把 Docker socket、`.env` 或整个用户 Home 暴露给 Serena。

### OpenSpec

规划完成后，在进入人工审批前先生成 OpenSpec change/spec，并执行：

```bash
openspec validate create-product --type change --strict --no-interactive
```

失败即停止流程。

### Structurizr DSL + C4 / diagrams

同一份 `ProjectSpec` 同时产生 C4 DSL、ER 元数据和 diagrams 部署图。完整模式还会用固定 Structurizr 镜像解析 `workspace.dsl`；因此 worker 需要按受控开发方式访问 Docker daemon。

Windows/WSL2 本地完整模式建议：

```bash
docker compose -f compose.yaml -f compose.sandbox.yaml up --build -d
```

`compose.sandbox.yaml` 会授予 worker Docker socket 权限，这等价于高权限主机能力，只适用于受信任本机开发，不应用于公网多租户 Worker。

### CubeSandbox

完整模式固定使用 CubeSandbox。平台上传自己生成的源码 ZIP，在沙箱中执行固定验证命令；模型文本不会被拼接到 shell 命令中。需要配置：

```text
FACTORY_CUBE_API_URL
FACTORY_CUBE_API_KEY
FACTORY_CUBE_TEMPLATE
```

### Coder

完整模式在打包后创建 Coder 长期 IDE 工作区。自动创建只允许 `FACTORY_CODER_OWNER_ID` 指定的管理员身份，避免普通用户借平台创建高权限工作区。

当前 Coder API 能真实创建 workspace；由于 Coder Template 的源码导入方式由用户部署的模板决定，返回值会明确标记 source import 状态，不能把“workspace 创建成功”冒充为“源码已自动导入并通过构建”。后续可在你的 Coder Template 中增加 Git/ZIP 初始化参数，把这一步完全自动化。

## 5. 完整模式与基础模式

**完整模式**强制：Serena/ToolHive + Cube + Coder，并检查所有指定组件配置。缺任何一项后端返回 422，不静默降级。

**基础模式**用于逐步调试，可以选择静态、Docker 或 Cube，并选择是否读取 Serena/Coder。它不会被标记成“所有组件已执行”。

工具链页的 `configured` 仅表示配置/依赖存在；真实运行的每个 Activity 还会产生 Event 和 stage_details。外部服务连接失败会让对应阶段失败。

## 6. 更新启动

```bash
git pull
python3 scripts/init_env.py
docker compose -f compose.yaml -f compose.sandbox.yaml up --build -d
```

检查：

```bash
docker compose ps -a
docker compose logs --tail=200 migrate api worker temporal
```

然后访问：

```text
http://localhost:8000/api/v1/web/#/factory
```

推荐首次顺序：

1. 进入“模型供应商”，添加一个真实模型并测试连接；
2. 进入“工具链中心”，确认完整模式所需组件；
3. 新建项目，观察 AI 提问并逐项回答；
4. 直到需求状态变成 READY；
5. 选择完整模式启动；
6. 审阅 OpenSpec/C4/结构化规格后人工批准；
7. 查看每个 Temporal 阶段、Cube 验证、ZIP 和 Coder 结果。

## 7. 验收原则

平台必须区分：

- configured：配置存在；
- reachable：真实探针/请求成功；
- used：本次 Run 的 Activity 实际执行；
- scaffold_ready：当前生成骨架通过约定检查；
- production_ready：只有完整部署、安全和业务验收真正做完后才能成立。

任何外部服务、模型、沙箱、架构 parser 或 Coder 未运行，都不能在 UI 或质量报告里冒充“全链路通过”。

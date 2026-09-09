# 联调前检查与部署：以本页为准

本页针对 `fix/workbench-integration-readiness`。旧手册中的固定 Demo、Structurizr 8081 和“Cube 只检查源码”等说明不适用于新版完整模式。最终验收状态以当前提交的 Actions 和报告为准，不能用旧提交的绿色状态代替。

## 1. 更新而不破坏数据

先备份数据库、`.env` 和 `data/` 到仓库外。不要执行 `down -v`。从仓库根目录，在 WSL/Linux 执行：

```bash
git fetch origin
git switch fix/workbench-integration-readiness
git pull --ff-only
python3 scripts/init_env.py
python3 scripts/setup_toolchain.py
docker compose up --build -d
docker compose ps -a
```

初始化只补缺失值，setup 只补空的安全网络默认值；不生成模型密钥，不删除现有数据。旧 PostgreSQL 卷的密码在本地 Unix socket 上同步为 `.env` 指定值，之后才启动迁移和 TCP 客户端。不要将这套本机开发的同角色多库配置直接用作公开多租户部署。

入口：`http://localhost:8000/api/v1/web/#/factory`。使用真正的 FastapiAdmin 登录。三个页面都嵌入现有壳，不再堆叠一套导航；消息、项目、工具清单内部滚动，主操作位于可见区域。

## 2. 模型与账号

`/factory-providers` 保存平台实际使用的 LiteLLM SDK profile，包括供应商、模型、Base URL、超时、有限重试和白名单参数。目录不是“所有模型都已测试”的清单，最终模型 ID、额度、结构化输出和地区权限由你的账号连接测试验证。

OpenAI API Key 与 ChatGPT/Codex 订阅授权是不同入口。订阅登录只在官方 `auth.openai.com` 页面由你完成，不在平台输入密码。按 profile/用户存储加密授权状态，调用使用独立临时子进程。断开授权是在平台清除令牌；需要撤销上游权限时也应在官方账号安全页面处理。不要连续新建多个相同账号配置来绕过上游授权速率限制。

切换供应商会清空尚未提交的凭据、模型、专用参数。已保存 profile 不支持变更供应商类型，需新建，避免把 A 家密钥发给 B 家。AWS 与 Vertex 凭据不能混入普通 API Key 配置。Vertex 只接受标准 service-account JSON，不接受文件路径、external_account 或自定义 token endpoint。

自定义模型 URL 必须获得管理员批准。**当前批准入口是 `.env`，不是工具链页面：**

```dotenv
FACTORY_MODEL_ALLOWED_ORIGINS=["http://litellm:4000","http://host.docker.internal:11434","https://models.example.com"]
```

只填写 origin，不能包含 `/v1`；供应商页 Base URL 再填实际 API 路径。修改后重新创建 API/worker 容器。TLS、DNS、出口防火墙与代理策略属于部署管理，不能靠应用 URL 校验取代。

### 独立 LiteLLM Proxy

```bash
docker compose --profile ai up -d litellm
```

管理页 `http://localhost:4000/ui`，默认用户名 admin；密码取 `LITELLM_UI_PASSWORD`，未配置时取你本地生成的 `LITELLM_MASTER_KEY`。不要公开这些值。Proxy 使用单独的 litellm 数据库，并不会接收整份平台 `.env`。

平台 profile 与 Proxy 数据库是两套明确的配置：平台直接 SDK 调用无须 Proxy；需要网关预算、路由、负载分配、虚拟密钥时在原生 Proxy UI 设置，并在平台添加 LiteLLM Proxy profile。导出的 YAML 只含环境变量引用，不含真实密钥，不会自动覆盖/重启现有网关。个人订阅 profile 被排除，不能变为所有用户共用的授权账号。

## 3. 每个工具实际配置什么

| 工具 | 已提供 | 需要操作 |
|---|---|---|
| FastapiAdmin | 固定模板、认证、权限、布局与接口 | 初始化登录后管理用户；全局工具设置只给超级管理员 |
| LangGraph | 需求澄清与规划图，结构化校验 | 在模型页选供应商；无需另起 LangGraph 服务 |
| Temporal | Compose 服务、Outbox、审批 signal | 默认即可；修改地址/命名空间/队列需要重启，不能在运行中随意切换 |
| OpenSpec | 固定 CLI，proposal/design/tasks/specs，strict 校验 | 镜像内置；完整模式必须有校验回执 |
| diagrams | Graphviz、部署 SVG、可编辑 Python 源 | 镜像内置；实际输出在规格审阅抽屉 |
| Structurizr/C4 | 生成 DSL，固定镜像解析与查看服务 | 启用 architecture profile；完整解析按下文配置受控 Docker runner |
| ToolHive/Serena | 管理代理的部署脚本，固定模板只读符号访问 | 部署真实 MCP，填 worker 可达地址与必要令牌，执行读取探针 |
| Cube | 官方基座全栈验收镜像配方、SDK 生命周期适配 | 部署 KVM/控制面，导入模板，填 URL/Key/Template ID |
| Coder | 可启动服务、Terraform 模板、源码 ZIP 自动导入 | 初始化账号/模板/provisioner，填 token、模板和 owner |
| LiteLLM | SDK 和可选原生网关管理页 | 模型 API/订阅必须由你授权 |

`/factory-toolchain` 每张卡可打开配置抽屉、文档、服务页面或探针。普通用户不读取敏感字段、不写全局设置。配置加密存于 PostgreSQL，API/活动使用有效设置，不是只保存一个 UI 标记。探针明确区分“依赖可用”“服务可达”和“必须运行验收”，不会偷偷创建计费沙箱。

**当前“恢复默认”已禁用**，因为旧存储实现删除版本行后可能让过期版本再次有效。接口也返回 409，不只是隐藏按钮。正常编辑和保存不受影响；需恢复时填入目标默认值并保存，不删除数据库配置记录。没有将未能写入的存储层改造冒充完成。

## 4. 内网地址与浏览器地址不要混用

### Coder

```bash
docker compose -f compose.yaml -f compose.tools.yaml --profile tools up -d coder
```

这是服务启动，不代表有可创建工作区的 provisioner。浏览器用 `http://localhost:7080`；同一 Compose 网络的平台后台用 `http://coder:7080`；工作区下载本次源码用 `http://api:8000`。

- `FACTORY_CODER_URL`：后台请求地址，也可在工具卡设置。
- `FACTORY_CODER_BROWSER_URL`：运行结果中的浏览器链接前缀，在 `.env` 设置；工具卡的“浏览器管理页”只控制卡片跳转，不会自动修改这个参数。
- `FACTORY_CODER_FACTORY_URL`：工作区访问平台的根地址，不能填工作区自身 localhost。
- `CODER_ACCESS_URL`：工作区 Agent 访问 Coder 的地址；本机默认 host.docker.internal:7080，远程部署必须换实际 DNS/HTTPS。

按 `integrations/coder/README.md` 构建工作区镜像并注册 Terraform 模板。服务 Token、Template ID、FastapiAdmin owner ID 由你配置，平台不捏造。若在同一可信开发机使用 Docker provisioner，可显式启用：

```bash
export DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)
docker compose -f compose.yaml -f compose.tools.yaml -f compose.coder-docker.yaml --profile tools up -d coder
```

该 override 给 Coder provisioner 主机级 Docker 权限，不适合不可信公网用户。生成的工作区本身不挂 Docker socket。更强隔离部署使用独立受控 provisioner。

### Structurizr

```bash
docker compose --profile architecture up -d structurizr
```

浏览器地址是 `http://localhost:8080`。查看根目录的 architecture 不等于某次 Run 的 DSL 已解析；Run 产物在平台审阅抽屉。

完整运行的 parser 需要 `FACTORY_DOCKER_HOST_DATA_DIR` 为实际 Linux/WSL 宿主 `data` 绝对路径。固定镜像通过显式 Java 入口和绝对 DSL 路径执行，避免镜像默认目录覆盖文件参数。可信本机可启用：

```bash
docker compose -f compose.yaml -f compose.sandbox.yaml up -d --force-recreate worker
```

该方案给 worker 主机管理员能力，不是生产隔离方案，不要把不可信生成命令或租户接到共享 socket。

### Cube 与 MCP

Cube 不能靠普通 Docker Compose 创造可用 KVM。部署外部 Linux/KVM 服务并注册 `integrations/cube/Dockerfile.fullstack` 对应模板，建议至少 6 GiB 内存。构建命令见 `docs/FINAL_CONSTRAINTS.md`。模板构建与导入 Cube 是两件事：CI 检查构建不代表你的 Cube 集群已注册它。

完整模式固定运行镜像内的 `full_stack.py`：独立临时 PG/Redis、前端构建与类型检查、原生登录、用户归属隔离；收到匹配输入 ZIP 哈希的回执后才可交付。普通 `source_only` 模板不能通过完整门禁。

ToolHive/Serena 按 `integrations/toolhive/README.md` 的 prepare/start/probe 操作。平台读取固定 Python 模板符号，非任意语言服务池。主机 loopback 不等于 worker 容器 loopback；保持认证和防火墙，不为连通而直接暴露未认证 MCP。

## 5. 真正的全流程验收

先在页面完成：配置模型 → 输入需求 → AI 追问 → 回答/确认 → 版本校验通过 → 开始流水线 → 审阅真实规格和架构 → 批准该 digest → 生成/验证 → ZIP → Coder 导入。

完整模式强制使用所有相应工具。任何组件缺失、跳过、失败、回执哈希不符都不能用 READY 掩盖。Run 冻结需求和验收快照；改变需求会重新澄清。管理员不要在执行中的任务切换全局工具服务或凭据。

也可在本地设置 `FACTORY_USER_JWT` 后执行（不把 JWT 放进命令行或 Issue）：

```bash
uv run python scripts/smoke_workbench.py --provider-id YOUR_PROFILE_ID --requirement requirements.txt --full --approve --accept-limitations
```

这两个批准参数代表你明确接受展示的规格与未支持项；未审阅时不要传。报告包括 `run-receipt.json`、`events.json`、源码 ZIP。Coder 回执在打包后生成，保存于平台 Run，不改写已验证的不可变 ZIP。

## 6. CI 与真实账号验证的区别

五个作业：`contracts`、`frontend-smoke`、`core-stack`、`coder-template`、`c4-contract`。前端截图是真实 SFC + Element Plus +嵌入壳，使用 API 夹具，不是登录截图。core-stack 使用真实 FastapiAdmin/PG/Redis/Temporal 和明确标识的模型 HTTP 夹具；真实支付模型、账号授权、Cube 集群与 MCP 网络仍需部署者联调。

成功回执只对应现有类型化 CRUD / 无环父子关联生成器。任意审批、计费、设备采集、复杂业务仍需实现，未支持项不得偷偷标为已完成；生产安全与浏览器业务验收不等于构建成功。公开部署前需独立授权速率限制、资源/费用上限、网络出口限制和备份策略。

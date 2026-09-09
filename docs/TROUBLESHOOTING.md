# 故障排查：先定位哪一段失败

## 构建前的问题

**docker: command not found / daemon 无法连接。** 检查 Docker Desktop 是否运行、WSL Integration 是否启用，执行 `docker version`。不要同时安装两套守护进程后混用 socket。

**git fetch 下载失败。** 检查 DNS、代理、证书、GitHub 访问与固定 SHA 是否可取。初始包不包含整个上游，网络是必要条件。不要私自改 master 以绕过失败，否则失去版本与 overlay 兼容保证。

**uv 解析冲突或 package not found。** 看具体依赖名称和索引。联合环境会保留上游 pin；不得无证据把上游版本降级。查看 `runtime/combined/pyproject.toml`，按官方仓库确认该提交是否要求特定索引/平台。网络镜像缺包和真实依赖冲突不是同一问题。Docker-first 启动路径不要求宿主机预装 uv，镜像内部会使用固定 uv 版本；`doctor.py` 中宿主机 `uv: missing` 本身不是启动阻塞。

**`init_env.py` 报 `FileExistsError: .../data`。** 这表示 `data` 这个路径已经存在，但不是可用目录，常见于覆盖旧工程后留下普通文件、坏符号链接或旧 bind-mount 链接。新版先检查 `data/` 再写 `.env`，不会再留下“`.env` 已生成但运行目录没有准备好”的半初始化状态。先执行：

```bash
python3 scripts/doctor.py
ls -ld data 2>/dev/null || true
file data 2>/dev/null || true
```

如果 `doctor.py` 的 `data_path.state` 是 `file`、`broken_symlink`、`symlink_file` 或 `other`，使用非破坏修复：

```bash
python3 scripts/init_env.py --repair-data
```

脚本不会删除原对象，而是先把它移动为 `data.conflict-<UTC时间>`，再创建新的 `data/`。如果 `data` 本来就是正常目录（包括指向目录的有效符号链接），即使带 `--repair-data` 也不会替换或清空其中内容。修复后再次运行 `python3 scripts/doctor.py`，应看到 `data_path.state` 为 `directory` 或 `symlink_directory`。

**pnpm lock 不匹配或 vue-tsc 失败。** 保留错误文件名，先检查 Node22、pnpm9.15.3 和下载的固定上游是否一致，再区分原上游代码还是 overlay 的 TypeScript 错误。不得删除 vue-tsc 命令来假装构建成功。overlay 在本次环境只做了 TypeScript 语法转译检查，没有运行完整 Vue 编译器。

## 启动的问题

**init-data 或 migrate exited。** exited(0) 是一次性成功；非零才是失败。先看：

```bash
docker compose ps -a
docker compose logs --tail=160 postgres postgres-auth-sync migrate
```

新版 `migrate` 会先输出 `Control-plane migration preflight:`。`managed`/`fresh` 会正常执行 Alembic；识别出完整旧结构时会显示 `legacy:rnd_0001` 或 `legacy:rnd_0002`，只写入匹配的 Alembic revision 后继续升级，不删除业务表。如果显示 `CONTROL_PLANE_SCHEMA_INCOMPATIBLE`，说明已有 `rnd_*` 是半迁移或未知结构；脚本会停止且不会 stamp/删表，应先备份并按诊断处理。

**PostgreSQL password authentication failed / PostgreSQL Healthy 但 migrate exit 1。** 覆盖源码、重新生成 `.env`，同时保留旧 `postgres-data` 卷时，卷中的 `factory` 角色仍可能保存旧密码；官方 Postgres 镜像不会因为容器环境变量变化自动修改已有集群密码。开发 Compose 现在增加 `postgres-auth-sync`：通过只在 Postgres 容器间共享的 Unix socket，把本地 `factory` 角色密码同步为当前 `.env`，然后用 TCP 再验证一次，成功后才允许 `migrate` 启动。它只修改登录凭据，不删除数据库、表或卷。检查：

```bash
docker compose logs --tail=120 postgres-auth-sync migrate
```

成功应看到 `PostgreSQL credential sync complete.`。不要为解决密码漂移直接执行 `docker compose down -v`。如果你主动修改过 `pg_hba.conf` 禁止本地 socket 认证，auth-sync 会失败并保持数据库不变，此时按你自己的 PostgreSQL 安全策略人工同步角色密码。

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

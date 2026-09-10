# 启动、升级和首次验收

本项目是需要首次联网构建的 AI 研发平台，不是完全离线包。固定 FastapiAdmin 模板通过 Docker 装配；模型账号与 Cube、MCP、Coder 的真实环境授权由部署者提供。完整配置以 [联调清单](INTEGRATION_ACCEPTANCE.md) 为准。

## 已有安装：先保留数据，再更新源码

升级前备份 `.env`、PostgreSQL 数据库、`data/` 和 Temporal 开发数据，确认备份能恢复。保留本地配置，不把秘密上传到 Git 或聊天。先执行 `git status`；存在本地修改时先保存，不使用 `reset --hard` 覆盖。

在 PR 分支验证本轮修复：

```bash
git fetch origin
git switch fix/workbench-integration-readiness
git pull --ff-only origin fix/workbench-integration-readiness
python3 scripts/doctor.py
python3 scripts/init_env.py
python3 scripts/setup_toolchain.py
docker compose config --quiet
docker compose up --build -d
docker compose ps -a
```

`init_env.py` 保留已有配置值，只补缺少的兼容设置；`setup_toolchain.py` 只补缺失或空白的本机工具地址，不生成模型 Key、Token、Template ID 或账号。配置若不适合你的远程部署，修改对应地址，不修改业务代码。主机未安装 uv 不阻止 Docker 路径，镜像内已经安装 uv。

不要把 `down -v`、`--fresh` 或 `-Fresh` 当作升级命令；它们会清空当前 Compose 项目的数据库卷。日常停机用 `docker compose stop`。`.env` 改动后使用 `docker compose up -d --force-recreate api worker`，单独 `restart` 不加载新环境变量。

## 新安装

Windows 使用启用了 WSL 集成的 Docker Desktop，在已有的 Ubuntu 终端操作。`docker version` 必须同时显示 Client 和 Server，`docker compose version` 必须可用。不要为了本项目在已有 Docker Desktop 后端旁边重复安装 dockerd。

```bash
mkdir -p ~/src
cd ~/src
git clone https://github.com/Live-yan/ai-rnd-foundation.git
cd ai-rnd-foundation
git switch fix/workbench-integration-readiness
bash scripts/start.sh
```

源码已有时不要重复克隆。主机 Python 用于初始化和诊断，应用 Python 环境由镜像安装。第一次构建会下载固定模板及依赖，不能在断网环境声称全部安装完成。

## 登录与配置

浏览器打开 `http://localhost:8000/api/v1/web/`，按固定 FastapiAdmin 模板的首次登录说明登录并立即修改初始化密码。研发入口为 `http://localhost:8000/api/v1/web/#/factory`；其他两个入口是 `#/factory-providers` 和 `#/factory-toolchain`。它们共用宿主登录和菜单体系，不要把 `FACTORY_TOKEN` 当成网页登录密码或 JWT。

先到模型供应商页配置自己的供应商、模型 ID 和相应凭据，并执行连接测试。API Key、云平台凭据和 ChatGPT/Codex 订阅授权是不同方式。连接失败时查看失败状态，平台不会静默切换到固定 Demo。自定义地址需在管理员 `.env` 的 `FACTORY_MODEL_ALLOWED_ORIGINS` 白名单中批准，详见联调清单。

不使用外部沙箱和 IDE 时可先选择**基础模式**验证需求澄清、规格审阅和源码导出；它明确记录跳过的工具，不等同完整产品验收。完整模式必须配置 ToolHive/Serena、Cube 模板、受控 Structurizr 执行和 Coder 自动导入。填写地址只是“配置存在”，不是“已执行成功”。

输入具体需求 → 回答 AI 的澄清问题 → 确认当前需求版本 → 开始流水线 → 检查真实规格/架构及未支持项 → 批准对应 digest → 验证 → 下载 ZIP。不要未审阅规格就自动批准。

## 故障定位

```bash
docker compose logs --tail=120 postgres-auth-sync migrate api worker temporal
```

`init-data`、`postgres-auth-sync`、`migrate` 等一次性服务正常结束为 `Exited (0)`；API、worker、数据库、Redis 和 Temporal 应持续运行。API 健康不等于 worker 已经成功执行任务。

出现大批 `Cannot find name 'ref' / 'computed' / 'ElMessage'` 时，检查是否还在运行旧 Dockerfile。本版先运行 Vite 生成自动导入声明，再执行 `vue-tsc --noEmit`；不删除类型检查，也不手工补几百个全局变量。资源路径为 `/api/v1/web/`，不是早期 `/web/`。

已有 PostgreSQL 卷与 `.env` 密码不一致时，启动链会同步本地开发角色密码并用 TCP 校验；不需要删除数据卷。同步失败先核对日志和实际挂载，不修改认证策略为公网 trust。

## 验收与生成产品

CI 使用一次性服务和明确标识的模型 HTTP 夹具，结果不能替代你的真实账号授权、Cube KVM/模板、MCP 网络和 Coder provisioner 联调。检查应绑定同一 Git 提交，并保留完整报告；失败、跳过、未运行均不能写成通过。

下载的产品解压到全新目录，按其中 README 和启动脚本独立运行，不覆盖平台源码，也不与平台共用数据库卷。用户隔离、关联约束、原生登录与 Redis 会话都应按报告和实际业务再次验收。当前确定性生成器支持类型化 CRUD 和无环父子关联；审批、支付、设备采集等未支持业务不能当成已经实现。

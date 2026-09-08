# 从零启动与首次验收

## 1. 你拿到的到底是什么

把这个目录理解为“建造平台的原料和装配说明”。Dockerfile 会下载你指定的真正 FastapiAdmin 固定提交，把新增研发平台代码接到它的应用工厂和 Vue 路由。它没有把一个极简 FastAPI 页面冒充完整 FastapiAdmin，也没有把上游 Agno 聊天功能当成整套软件研发流水线。

但是，本包 **不是完全离线包**，本次环境 **没有实际启动 Docker 整栈**。因此请把首次本机验收视为必要步骤。若你要求“下载即离线运行、11 个工具全部已联调、任意需求都生成完整产品”，本包尚未达到这一标准。

## 2. Windows + AMD 的准备工作

推荐 Windows + WSL2 Ubuntu + Docker Desktop，源码放在 Ubuntu 的 `~/src`，而不是长期从 `/mnt/c` 的 Windows 文件夹运行大量 Linux 构建。AMD 指处理器架构，不代表一定有 GPU，也不代表自动具备 KVM。模型可以放远端；不要求本机显卡。[S13][S14]

第一步，在 Windows 任务管理器的“性能 → CPU”查看虚拟化是否已启用。未启用时按主板说明进入 BIOS 开启 SVM/AMD-V。管理员 PowerShell 执行：

```powershell
wsl --install -d Ubuntu-24.04
wsl --update
wsl --list --verbose
```

如果 Ubuntu 已经安装，不重复安装，确认 VERSION 一列为 2。首次打开 Ubuntu 会要求设置 Linux 用户名和密码；输入密码时没有星号是正常现象。

第二步，安装 Docker Desktop，选择 WSL2 后端，在 Settings → Resources → WSL Integration 中启用你的 Ubuntu。打开 Ubuntu 终端执行：

```bash
docker version
docker compose version
```

成功时应同时看到 Docker Client 和 Server。只有 Client 而 Server 连接失败，说明 Docker Desktop 未启动或 WSL 集成未启用。不要在同一个 WSL 里盲目再安装另一套 dockerd。

第三步，准备终端工具并解压。把下面 Windows 路径换成你真实下载位置：

```bash
sudo apt-get update
sudo apt-get install -y git unzip python3 ca-certificates
mkdir -p ~/src
cd ~/src
unzip /mnt/c/Users/你的Windows用户名/Downloads/AI_RND_Platform_Foundation_0.1.0.zip
cd ai-rnd-foundation
ls
```

应能看见 `Dockerfile`、`compose.yaml`、`factory`、`scripts`、`docs`。终端中的当前目录很重要：后文未特别注明的命令，都在这个项目根目录运行。

你可以在 Windows 安装 VS Code 及 WSL 扩展，在 Ubuntu 根目录执行 `code .` 打开整个项目。先不用理解全部源码。

## 3. 第一次只运行核心流程

暂不安装 Cube、Coder、ToolHive，也不填模型密钥。先验证基础工程，避免 11 个服务同时报错。

```bash
python3 scripts/doctor.py
python3 scripts/init_env.py
docker compose config --quiet
docker compose up --build -d
```

`init_env.py` 只在 `.env` 不存在时生成随机 PostgreSQL、Redis 和 JWT 密钥，不覆盖已有配置。`.env` 是本机秘密，不能上传 Git、聊天截图或发给编程 AI。`docker compose config --quiet` 只检查配置；不要把展开的 `docker compose config` 输出公开，因为它包含密码。

也可以用 `bash scripts/start.sh` 执行初始化和启动。这个脚本不是隐藏式安装器，你可以先打开查看内容。

首次构建依次进行：拉取固定上游 → 组装新增 Vue 页面 → pnpm 安装和类型检查 → 前端构建 → uv 解析平台与上游共同依赖 → 安装 → 启动 PostgreSQL、Redis、Temporal → 平台迁移 → API/worker 启动。任一步失败，必须保留并检查失败位置；不能删除类型检查、跳过迁移或改成 demo 后就宣称已修好。

```bash
docker compose ps -a
docker compose logs --tail=120 migrate api worker temporal
```

`init-data`、`migrate` 正常完成后显示 exited(0) 是正常的，它们是一次性任务。API/worker/PG/Redis/Temporal 应持续运行。健康检查只覆盖对应服务，API health 成功不意味着 worker 已执行任务。

## 4. 登录并找到新增研发界面

浏览器打开 `http://localhost:8000/web/`。上游当前 README 的本地快速启动说明使用 `admin / 123456`；首次登录后立即改密码，删除不需要的演示用户。原始模板的账号初始化逻辑未在本次环境实际运行，若登录失败查看 API 初始化日志和下载的上游说明，不尝试猜测数据库密码。[S01]

登录后地址栏输入：

```text
http://localhost:8000/web/#/factory
```

这是新增的独立研发页面，默认没有自动写入 FastapiAdmin 菜单数据库。以后可按上游菜单管理方式加一个可见菜单入口。`/web/#/factory` 中 `#` 后面是浏览器路由，不是后端文件路径。

页面使用原来的登录令牌，后端复用 JWT、Redis 会话以及实时用户检查。不要把 `FACTORY_TOKEN` 粘进去；它只用于可选诊断应用，不是主界面的登录凭据。

## 5. 先跑明确标识的 demo

填写项目名称“设备台账演示”，需求填写“建立设备与维修记录管理，验证台账和关联记录”。选择唯一已实现的 `fastapiadmin-pg-v1` 模板；provider 选择 demo，sandbox 选择 static，暂不勾 Serena。

demo 总是生成同一套设备和维修记录结构。它的作用是排除模型差异、验证装配链，不会把你输入的任意软件需求真正实现。页面会展示该限制，必须主动认可才能批准。

点击启动后，状态顺序应为：

```text
QUEUED → PLANNING → AWAITING_APPROVAL
       → GENERATING → VERIFYING → PACKAGING → READY
```

在审批页检查表、字段、引用和未实现项。确认后点击批准；不接受就拒绝，补充需求后新建一个 run。当前不支持直接在审批页编辑 JSON。后补的聊天消息不会修改正在运行任务的需求快照。

READY 表示 **通过本版门禁的源码骨架可下载**，不是生产验收合格。点击下载，保存 ZIP，打开其中的 `delivery/quality.json`。如果状态 FAILED，先看事件和 worker 日志，不重复点几十次创建任务。

## 6. 在干净目录启动下载的产品

把下载 ZIP 解压到一个新目录，不要覆盖平台自身目录。这是“被生成的软件”，与“生成软件的平台”是两个独立项目。

```bash
cd ~/src/你解压后的产品目录
python3 scripts/init_product.py
docker compose config --quiet
docker compose up --build -d
docker compose logs --tail=100 app
```

产品默认网页 `http://localhost:8010/web/`；登录并改密码后打开 `http://localhost:8010/web/#/business`。先新增一个设备，记住 ID，再新增引用它的维修记录。关联字段目前填写父记录 ID，并非智能下拉选项。

至少验收：刷新后数据仍在；重启 app 后数据仍在；第二个用户看不到第一个用户的业务记录；跨用户引用被拒绝；有子记录的父记录不能直接删除。不要因为看到了表单就认为数据库或权限已验收。

平台与产品默认端口不同。运行多个产品时，为每个产品修改 Compose 项目名和端口，不能共用同一组数据卷或照抄密码。

## 7. 让真实需求进入模型

只有先跑通上面的固定 demo，才接真实模型。已有 Ollama 时，在其所在机器运行 `ollama list`，复制一个确实已安装、支持聊天并能稳定输出 JSON 的模型名。不要照抄手册中的占位符，也不要凭显存大小假定任意模型都能运行。

编辑平台根目录 `.env` 的 `OLLAMA_MODEL`，然后执行：

```bash
python3 scripts/configure_model.py
docker compose --profile ai up -d --force-recreate api worker litellm
docker compose exec worker python scripts/probe_integrations.py model
```

脚本为 LiteLLM 生成 `factory-planner` 路由，将平台模型密钥设置为网关 master key。默认网关访问 `http://host.docker.internal:11434` 的 Ollama；本机部署位置和绑定地址不同时需要修改 `integrations/litellm/config.yaml`。不要为了 Docker 连通而把无认证 Ollama 暴露公网。[S09]

探针成功后在网页选择 litellm，输入一个小而具体的需求，例如：“仓库货架管理，货架有名称、区域、启用状态；物品有名称、数量、所属货架，只做台账 CRUD，不做出入库交易。”模型产出的字段应与本次需求一致，不应仍然固定出现维修记录。

数量约束、唯一编码、库存扣减事务等不属于本版自动完成能力。模型应将未支持项列出；你仍需人工检查它有没有遗漏。模型返回 400、超时或非法 JSON 时会失败，不偷偷切换到 demo。

## 8. 开关服务、记录版本

```bash
# 普通停止，保留数据库：
docker compose stop
# 继续：
docker compose up -d
# 编辑 .env 后：
docker compose up -d --force-recreate api worker
# 成功构建后记录真实依赖：
bash scripts/capture_locks.sh
```

不要把 `restart` 当成重新载入 Compose 环境变量；修改 `.env` 通常需要 recreate。不要把 `down -v` 当成日常停止。升级前备份 `.env`、PostgreSQL、产物目录和 Temporal 开发数据，并实际演练恢复。

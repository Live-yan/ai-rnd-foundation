# ToolHive + Serena：可执行部署配方，尚未进行真实服务联调

本目录配合 `factory/providers/mcp.py` 使用。不是装好一个容器就宣称“安全的多租户 MCP 已完成”。当前只读取一份固定 FastapiAdmin 模板；没有项目切换、自动语言服务器选择和每用户 MCP 实例池。

## 1. 准备

在 WSL Ubuntu、项目根目录操作。安装官方 ToolHive CLI 后，执行 `thv version`、`thv run --help`，确认支持 `--tools`、`--proxy-port`、`--target-port` 和 `--volume`。安装入口见手册来源 S08。

```bash
bash integrations/toolhive/prepare.sh
```

脚本第一次解析 Serena HEAD，把实际 SHA 写入 `locks/serena.ref`，以后复用，不追随最新提交。它创建独立模板副本、Python 3.13 Serena 镜像并初始化索引。这里的 SHA 是你本地首次执行时取得的，不是本包已验证的版本。初始化失败时停止；不要为了继续而伪造 `.serena/project.yml`。检查 `project create --help` 和语言服务器安装日志。

```bash
bash integrations/toolhive/start.sh
```

ToolHive 在主机 `127.0.0.1:9122` 代理 MCP，Serena 在容器内 9121 提供 streamable HTTP。模板代码只读；只有模板自己的 `.serena` 缓存和服务配置可写。不要挂载 `/`、用户 Home、平台 `.env`、整个 `data/` 或 Docker socket。此示例容器尚未做完整镜像加固，不面向不可信公网用户。

## 2. 核验而不是只看容器运行

主机测试环境设置 `FACTORY_SERENA_URL=http://127.0.0.1:9122/mcp`，然后用包含 MCP 依赖的 Python 环境执行：

```bash
uv run python scripts/probe_integrations.py serena
```

成功必须同时完成 MCP initialize、list_tools、get_symbols_overview。脚本失败即未接通，不能降级为“已集成”。固定模板的 Python 文件应在返回符号中可辨认。

Docker worker 内的 `127.0.0.1` 是 worker 自己，不能照抄主机地址。Docker Desktop 对 `host.docker.internal` 与主机 loopback 的可达性因部署方式不同，必须在 worker 内实测。不要一遇到连接失败就把未认证 MCP 暴露到 `0.0.0.0`。使用私有网络接口、明确的防火墙来源限制及 ToolHive OIDC/mTLS 认证代理，或先在同一 WSL 主机运行 worker。若采用 Bearer 认证，设置 `FACTORY_SERENA_TOKEN` 为服务验证的短期凭据；填一个任意字符串不会自动建立认证。

把实际可达的 `/mcp` URL 配置到平台 `.env`，重建 api/worker 容器并重新执行探针：

```bash
docker compose up -d --force-recreate api worker
docker compose exec worker python scripts/probe_integrations.py serena
```

## 3. 安全边界

ToolHive 负责启动、代理、权限与工具暴露；Serena 提供符号级代码理解。应用内 allowlist 是第二层限制，不替代服务器侧过滤。未来增加自由编码时，必须为每个工作区创建独立实例，分离读写工具，不能把一个有活动项目状态的 Serena 实例共享给不相关用户。默认基础流程不选 Serena 仍可运行。

## 4. 已知未验证事项

本包没有运行 ToolHive 或 Serena，也没有验证此版本 LSP 初始化在只读模板条件下的全部行为。先通过上述真实探针，再启用 UI 的 Serena 选项。运行探针只证明读取接口可用，不代表任意编程语言均已可用。

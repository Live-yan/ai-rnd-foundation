# ToolHive + Serena：只读模板 MCP

本目录配合 `factory/providers/mcp.py` 使用。不是装好一个容器就宣称“安全的多租户 MCP 已完成”。当前只读取一份固定 FastapiAdmin 模板；没有项目切换、自动语言服务器选择和每用户 MCP 实例池。

## 1. 准备

在 WSL Ubuntu、项目根目录准备镜像。Windows Docker Desktop 可使用原生 ToolHive CLI 启动代理；本次实测版本为 **v0.49.0**，下载官方 release 并核对 checksums，将 `thv.exe` 放在 PATH 或 `runtime/toolhive/thv.exe`。Linux 使用同版本 `thv`。`--tools` 必须分别传递，不能把四个工具名作为一个逗号字符串（该版本会因此过滤掉全部工具）。

```bash
bash integrations/toolhive/prepare.sh
```

`locks/serena.ref` 固定本次验证的 Serena 提交。脚本创建独立模板副本、Python 3.13/Node 22 Serena 镜像并初始化索引；已有项目执行 `project index`，可重复运行。缺少 lock 时才解析 HEAD 并记录。初始化失败时停止，不伪造 `.serena/project.yml`。Node 和 libatomic1 已装入镜像，解决 Pyright 启动依赖缺失。

```bash
bash integrations/toolhive/start.sh
```

Windows 原生代理（不要同时在 WSL 和 Windows 启动同名代理）：

```powershell
powershell -ExecutionPolicy Bypass -File integrations/toolhive/start.ps1
```

脚本会恢复已有 workload；只有尚未创建时才注册。更改挂载/allowlist 后需先明确移除该 workload 再创建（不删除模板 bind mount）。

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

## 4. LiteLLM 转发与本机实测

本次 Windows Docker Desktop 已验证 `LiteLLM → host.docker.internal:9122 → ToolHive → Serena`，工具列表严格为四个只读工具。平台 `FACTORY_SERENA_URL=http://litellm:4000/serena/mcp`，`FACTORY_SERENA_TOKEN` 使用限定 server ID 的 LiteLLM 虚拟密钥。客户端兼容 `serena-get_symbols_overview` 前缀，不使用任意后缀匹配。

该地址只适合已实测可达的 Docker Desktop 主机代理。其他 Linux 部署需改成实际私网地址并重新测试，不能为连通而开放未认证公网端口。平台、代理和 Gateway 均已实际读取四个固定模板文件；不代表任意语言服务池、多租户隔离或生产安全已验收。

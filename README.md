# AI 软件研发平台 · FastapiAdmin

面向非技术用户的模板交付工作台：选择模板、描述需求、确认范围、生成并验收、下载启动。复用 LiteLLM、LangGraph、Temporal 和模板原有能力。FastapiAdmin 与芋道 Cloud Mini + Vue3 Ant Design Vue 两套模板均已接入，并通过固定规格运行验收。

**当前操作入口与能力边界：[从模板到可运行交付](docs/NO_CODE_DELIVERY.md)。** 默认运行验收实际构建前端并检查数据库、登录和 CRUD；“仅源码检查”单独标记。交付包新增启动器，自动分配端口并打开浏览器。

## 当前工具范围

CubeSandbox 和 Coder 已从工作台工具链、配置/探测入口和新任务选项移除。新任务使用 core 源码交付流程，可选 static / Docker 检查与 Serena；不再提供依赖这两项的 full 模式。历史记录、凭据和适配器仅保留兼容，不删除既有服务或数据。`--tools` 不再自动启动 Coder，遗留服务需显式 `--profile legacy-coder`。code-server 不受影响，尚未新增其自动源码导入能力。

下方及早期验收文档中的 Cube/Coder 完整链路说明只供历史参考，不代表当前新任务入口仍支持。

## 当前入口

新流程启动、Luna 模型配置和试用步骤优先阅读 **[从模板到可运行交付](docs/NO_CODE_DELIVERY.md)**；通用联调参考 [联调前检查与部署](docs/INTEGRATION_ACCEPTANCE.md)。

```bash
python3 scripts/init_env.py
python3 scripts/setup_toolchain.py
docker compose up --build -d
```

以上为基础启动。测试新的实际运行验收需使用 `docker compose -f compose.yaml -f compose.runtime.yaml --profile ai up -d`，并预先准备运行验收镜像与芋道源码；当前开发机已完成准备，完整 PowerShell 命令见上述操作说明。

Windows 用户在已启用 Docker Desktop WSL 集成的 Ubuntu 中执行。首次在线下载固定提交 `f7f5fb61a5c918016640f6b07e053c807381b7cc`，不追随上游 main。入口：`http://localhost:8000/api/v1/web/#/factory`。

本机已准备 ToolHive/Serena 后，可运行 `powershell -File scripts/start.ps1 -Tools`（Linux：`bash scripts/start.sh --tools`）一并启动 LiteLLM 和官方 Structurizr MCP/查看页。该旧启动脚本不包含新运行验收 override；新流程使用上述专用命令。连接拓扑与实测证据见 **[本机连接记录](docs/LOCAL_CONNECTIONS.md)**。

三个嵌入页面：研发工作台、模型/LiteLLM 配置、工具链配置。普通模型 API Key、云平台凭据和个人 ChatGPT/Codex 授权分开；由用户自己完成真实账号授权。

## 范围与验证

确定性生成器支持类型化 CRUD、用户数据归属和无环父子关联。不能实现的需求列为未支持项，不能把任意软件需求误称完成。完整模式要求 OpenSpec、C4/Structurizr、diagrams、ToolHive/Serena、Cube 全栈验收与 Coder 源码导入回执；基础模式明确记录跳过项。

Actions 检查 Python 合同、前端构建/类型/四种视口、真实核心服务与生成产品、工具镜像和 Coder 模板。**当前提交是否通过请查看其 Checks**；夹具模型不代表真实账号、外部 Cube/KVM、MCP 或生产安全已联调。

五项检查全部成功后，`delivery` 作业会再次核对同次运行的证据和哈希，生成 `verified-delivery` 源码包、证据包、依赖锁及校验清单。失败/跳过/取消不会发布通过验收的交付包。详见 [当前交付门禁](docs/VALIDATION_REPORT.md)。

## 文档

- [联调清单、各工具配置与服务地址](docs/INTEGRATION_ACCEPTANCE.md)
- [本机 MCP 连接、真实模型与工作流实测](docs/LOCAL_CONNECTIONS.md)
- [最后约束与全栈验收器](docs/FINAL_CONSTRAINTS.md)
- [框架与 Agent 扩展](docs/EXTENDING.md)
- [给编程 AI 的实施提示词](docs/AI_PROMPTS.md)
- [详细手册（历史设计，部署细节以联调清单为准）](docs/HANDBOOK.md)
- `integrations/`：具体模板、服务配方与执行边界。

升级先备份 `.env`、数据库和 `data/`。正常停止用 `docker compose stop`，不要对真实数据运行 `down -v`。本机配置、Docker socket override 和共享开发数据库角色不适合直接向不可信租户开放。

原创代码 MIT，上游保留各自许可证，见 `THIRD_PARTY_NOTICES.md`。

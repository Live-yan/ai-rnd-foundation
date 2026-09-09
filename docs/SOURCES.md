# 官方来源与版本核对

资料核对基线：2026-09-08。以下用于确认工具职责、公开接口和版本；它们不是本平台已完整联调的证明。代码中的组合架构、状态机、边界、脚本和测试由本包实现。网络资料可能更新，首次部署后应保存实际版本和摘要。

- [U01] 用户旧规划：AI_SOFTWARE_RND_PLATFORM_MASTER_PLAN(2).md。参考Golden Template、Architecture Pack、Provider和确定性验收原则；当前请求优先。
- [S01] FastapiAdmin官方仓库与固定提交： https://github.com/fastapiadmin/FastapiAdmin/tree/f7f5fb61a5c918016640f6b07e053c807381b7cc 。已核对backend/app/__init__.py、core/dependencies.py、pyproject.toml、frontend/web/package.json、router/index.ts、utils/auth/index.ts及环境样例。当前公开README：https://github.com/fastapiadmin/FastapiAdmin 。注意不是另一个名为fastapi-admin的TortoiseORM项目。
- [S02] OpenSpec官方仓库、CLI、1.12.0包定义：https://github.com/Fission-AI/OpenSpec ； https://github.com/Fission-AI/OpenSpec/blob/main/docs/cli.md ； https://github.com/Fission-AI/OpenSpec/blob/main/package.json 。
- [S03] LangGraph官方仓库：https://github.com/langchain-ai/langgraph 。
- [S04] Temporal官方仓库与CLI开发服务：https://github.com/temporalio/temporal ； https://docs.temporal.io/cli/setup-cli ； https://github.com/temporalio/cli/releases 。开发CLI镜像使用1.8.3；镜像是否可在你的registry拉取仍需实测。
- [S05] Structurizr统一工具与DSL：https://docs.structurizr.com/dsl ； https://docs.structurizr.com/binaries ； https://docs.structurizr.com/local ； https://docs.structurizr.com/validate ； https://docs.structurizr.com/export 。已核对2026.06.28系列二进制、local/validate/export与旧Lite/CLI停止维护说明；本包用local而非需要另行评估许可的协作server。
- [S06] CubeSandbox官方仓库及E2B示例：https://github.com/TencentCloud/CubeSandbox ； https://github.com/TencentCloud/CubeSandbox/tree/master/examples/code-sandbox-quickstart 。已核对E2B_API_URL、e2b-code-interpreter、Sandbox.create、allow_internet_access、files/commands路径与KVM前提。
- [S07] Coder官方安装与工作区API：https://github.com/coder/coder ； https://coder.com/docs/install/docker ； https://coder.com/docs/reference/api/workspaces 。
- [S08] ToolHive官方仓库与thv run参数：https://github.com/stacklok/toolhive ； https://docs.stacklok.com/toolhive/reference/cli/thv_run/ 。已核对streamable-http、tools过滤、volume、proxy-port、target-port、host及网络/认证相关参数。
- [S09] LiteLLM官方仓库及代理部署：https://github.com/BerriAI/litellm ； https://docs.litellm.ai/docs/proxy/docker_quick_start 。镜像main-stable是可变标签，必须在本机验证后锁digest。
- [S10] Serena官方仓库与运行说明：https://github.com/oraios/serena ； https://oraios.github.io/serena/02-usage/020_running.html 。核对Python3.13、uvx、MCP服务、project create/index/health-check及项目作用域。
- [S11] OpenHands SDK与Docker Agent Server：https://docs.openhands.dev/sdk/arch/overview ； https://docs.openhands.dev/sdk/getting-started ； https://docs.openhands.dev/sdk/guides/agent-server/docker-sandbox 。本包建议作为第二阶段自由编码候选，不声称已替你完成其生产适配。
- [S12] LangChain DeepAgents官方文档：https://docs.langchain.com/oss/python/deepagents/overview 。可作为后续编排/上下文管理比较对象，本包未引入其运行依赖。
- [S13] Microsoft WSL安装与开发环境：https://learn.microsoft.com/en-us/windows/wsl/install ； https://learn.microsoft.com/en-us/windows/wsl/setup/environment 。
- [S14] Docker Desktop WSL2后端：https://docs.docker.com/desktop/features/wsl/ 。
- [S15] Astral uv安装与版本：https://docs.astral.sh/uv/getting-started/installation/ ； https://github.com/astral-sh/uv/releases 。构建工具锁定0.12.10；业务依赖的完整锁须实际解析。
- [S16] mingrammer diagrams与Graphviz前提：https://github.com/mingrammer/diagrams ； https://diagrams.mingrammer.com/docs/getting-started/installation 。

本包不内置第三方字体文件，不重新许可第三方源代码。具体许可证和供应链审计见THIRD_PARTY_NOTICES.md。

# AI 软件研发平台 · FastapiAdmin

基于固定 FastapiAdmin 模板、uv、PostgreSQL、Vue3、LangGraph 与 Temporal 的规格驱动软件工厂。模型通过 LiteLLM profile 配置；网页工作台先澄清需求，再审阅规格/架构、批准、生成、验证并下载源码。

## 当前入口

优先阅读 **[联调前检查与部署](docs/INTEGRATION_ACCEPTANCE.md)**。该文档取代早期手册里固定 Demo、旧服务端口和仅源码检查的说明。

```bash
python3 scripts/init_env.py
python3 scripts/setup_toolchain.py
docker compose up --build -d
```

Windows 用户在已启用 Docker Desktop WSL 集成的 Ubuntu 中执行。首次在线下载固定提交 `f7f5fb61a5c918016640f6b07e053c807381b7cc`，不追随上游 main。入口：`http://localhost:8000/api/v1/web/#/factory`。

三个嵌入页面：研发工作台、模型/LiteLLM 配置、工具链配置。普通模型 API Key、云平台凭据和个人 ChatGPT/Codex 授权分开；由用户自己完成真实账号授权。

## 范围与验证

确定性生成器支持类型化 CRUD、用户数据归属和无环父子关联。不能实现的需求列为未支持项，不能把任意软件需求误称完成。完整模式要求 OpenSpec、C4/Structurizr、diagrams、ToolHive/Serena、Cube 全栈验收与 Coder 源码导入回执；基础模式明确记录跳过项。

Actions 检查 Python 合同、前端构建/类型/四种视口、真实核心服务与生成产品、工具镜像和 Coder 模板。**当前提交是否通过请查看其 Checks**；夹具模型不代表真实账号、外部 Cube/KVM、MCP 或生产安全已联调。

五项检查全部成功后，`delivery` 作业会再次核对同次运行的证据和哈希，生成 `verified-delivery` 源码包、证据包、依赖锁及校验清单。失败/跳过/取消不会发布通过验收的交付包。详见 [当前交付门禁](docs/VALIDATION_REPORT.md)。

## 文档

- [联调清单、各工具配置与服务地址](docs/INTEGRATION_ACCEPTANCE.md)
- [最后约束与全栈验收器](docs/FINAL_CONSTRAINTS.md)
- [框架与 Agent 扩展](docs/EXTENDING.md)
- [给编程 AI 的实施提示词](docs/AI_PROMPTS.md)
- [详细手册（历史设计，部署细节以联调清单为准）](docs/HANDBOOK.md)
- `integrations/`：具体模板、服务配方与执行边界。

升级先备份 `.env`、数据库和 `data/`。正常停止用 `docker compose stop`，不要对真实数据运行 `down -v`。本机配置、Docker socket override 和共享开发数据库角色不适合直接向不可信租户开放。

原创代码 MIT，上游保留各自许可证，见 `THIRD_PARTY_NOTICES.md`。

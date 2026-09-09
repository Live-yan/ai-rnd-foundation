# AI 软件研发平台基础工程 · 0.1.0

**FastapiAdmin + uv + PostgreSQL + Vue3 + LangGraph + Temporal。**

这是一个含实际代码、模板组装脚本、工作流、生成器、UI、适配器、测试和中文手册的在线组装基础工程。不是只画架构图的规划；也不是已经在本次交付环境通过完整部署验收的成品 SaaS。

## 先读这三件事

1. **初始 ZIP 不内置整个 FastapiAdmin 仓库、依赖或镜像。** 首次 `docker compose build` 在线拉取固定提交 `f7f5fb61a5c918016640f6b07e053c807381b7cc` 并组装；不是拉取不确定的 master。之后平台生成的产品 ZIP 才包含实际上游源代码和业务扩展。
2. **真实生成范围是类型化 CRUD + 无环父子关联。** Demo 是明确标识的固定设备台账，不是假装理解任意需求。真实需求使用 LiteLLM 模式，需要你配置可用模型。审批、计费、复杂报表、任意第三方集成等不会自动完成。
3. **当前交付环境通过的是本地单元/契约测试，不是完整上游部署。** Docker/PG/Temporal/LangGraph/模型及远端服务尚未在这里完成联调。请先执行手册的真实验收，不直接上线或宣称生产可用。

## 最短启动入口

在 Windows 的 WSL Ubuntu 中，解压本包并进入项目根目录：

```bash
python3 scripts/doctor.py
bash scripts/start.sh
```

Docker Desktop 必须已运行并启用此 Ubuntu 的 WSL 集成；第一次需要网络下载。构建失败时查看原始错误，按 `docs/TROUBLESHOOTING.md` 排查，不跳过类型检查或质量门禁。

FastapiAdmin 使用 `ROOT_PATH=/api/v1`，因此本地直接访问 Uvicorn 时，前端公开路径是 `http://localhost:8000/api/v1/web/`。登录并修改初始化密码后，打开 `http://localhost:8000/api/v1/web/#/factory`。不要使用旧的 `/web/` 地址；它不包含 FastAPI root path。

建项目 → 选择 demo 或已配置的 litellm → 生成规格 → 查看未支持项 → 明确批准 → 等待源码检查 → 下载 → 新目录启动产品。

## 文档入口

- `docs/START_HERE.md`：从 Windows/WSL 开始，第一次跑通流程。
- `docs/HANDBOOK.md` 与 `docs/HANDBOOK.pdf`：完整中文手册，架构、工具关系、数据流、扩展路线、AI 提示词。
- `docs/VALIDATION_REPORT.md`：测试范围与未执行事项。
- `docs/EXTENDING.md`：增加其他框架/Agent/图表的方法。
- `docs/AI_PROMPTS.md`：可直接交给编程 AI 的分阶段提示词。
- `integrations/`：ToolHive/Serena、Coder、Cube、LiteLLM、OpenHands 的具体配置与边界。

## 运行与停止

```bash
docker compose ps
docker compose logs --tail=100 api worker
docker compose stop
# 恢复现有数据：
docker compose up -d
```

不要把 `docker compose down -v` 当成普通停止；它会删除命名数据卷。`.env` 不提交，`data/` 不公开，生产环境不使用默认账户和本地开发配置。

本基础工程的原创代码使用 MIT。上游项目各自保留许可证，见 `THIRD_PARTY_NOTICES.md`。

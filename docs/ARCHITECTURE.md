# 架构、职责与数据流

## 1. 产品目标：先建立可信的交付闭环

我们要建设的是“软件工厂”，不是单纯聊天窗口，也不是把十一个开源项目同时启动起来。用户需求必须转换为明确规格；模板必须可追溯；生成动作必须受限；质量证据必须能够复查；交付包必须离开平台独立运行。

本版刻意收窄到 Python/FastAPI + Vue3 + PostgreSQL 的管理型应用。固定模板保留上游管理框架，扩展独立业务 schema、迁移、CRUD 路由和动态 Vue 业务页面。它并未自动生成每个模块完整的上游 controller/service/crud/model 四层文件；当前业务扩展采用一个可阅读、可测试的类型化运行时。下一阶段可换成四层源码 renderer，而不必推翻平台工作流。

原规划强调 Golden Template、Architecture Pack、Provider、确定性验收，这些保留。默认 GitHub PR、并行集群和必须先有 Coder/Cube 的顺序被取消。先下载可运行产品，再增加代码托管、自由编码和多人协作。[U01]

## 2. 五个职责区域

**用户入口**是 FastapiAdmin 管理壳及新增 Vue 页面。原来的用户、角色、登录和会话不重写。平台研发功能放在 `/factory-api`，产品业务功能放在 `/business-api`，避免与上游版本化 API 命名冲突。

**平台控制层**是 `factory/api.py`、Repository、PostgreSQL、事务 outbox。它记录项目、消息、运行、审批、事件和产物路径，不在 HTTP 请求里直接运行几分钟的 AI 工作。

**编排层**由 Temporal 和 LangGraph 分工。Temporal 处理跨阶段的可靠执行、等待、重试和状态恢复；LangGraph 在一次规划 activity 内完成 draft/validate 的有界循环，不再建立第二套持久任务调度系统。[S03][S04]

**生成与验证层**用固定提交的模板、确定性业务 renderer、OpenSpec 文档、Graphviz/diagrams、源码与业务契约测试。模型不能直接写任意文件、数据库 URL、Dockerfile 或 shell 命令。这是本版安全边界，不是为了装饰而加入“多 Agent”。

**开发与隔离层**为可选 Coder、Docker verifier、Cube。Coder 保存长期 IDE 工作；Cube 提供临时 MicroVM；Docker verifier 是本地测试的受限命令运行器。它们不是同一个文件系统，更不能默认共享主机全部目录。[S06][S07]

## 3. 逻辑关系图

```text
用户 / FastapiAdmin Vue 页面
         │ 登录身份 + 需求消息
         ▼
Factory API ──事务──► PostgreSQL(rnd_*) + outbox
                             │
                             ▼
                      Outbox Dispatcher
                             │ workflow-id = run-id
                             ▼
Temporal：plan → 等待批准 → generate → verify → package
            │                    │          │         │
            ▼                    ▼          ▼         ▼
       LangGraph             模板工厂     门禁报告    ZIP + SHA
       draft/validate        固定上游        │         │
         │     ▲              + overlay      │         ▼
         │     └─ToolHive→Serena            Docker/Cube 用户下载
         ▼                 （只读模板）      （可选）      │
       LiteLLM ──► 本地或远端模型                        ▼
                                              VS Code / IDEA / Coder
```

`architecture/workspace.dsl` 是平台的 C4 源文件；生成产品中的同名文件描述该产品，两者不能混为一张图。`architecture/platform.svg` 是本包绘制的逻辑关系图，不是 Structurizr 已完成解析的证明。

## 4. 工具职责与当前接入程度

| 工具 | 在项目中的工作 | 本包实现 | 本次真实运行情况 |
|---|---|---|---|
| FastapiAdmin | 平台管理壳、产品 Golden Template | 固定提交组装、复用鉴权、追加 Vue 路由 | 未完整下载或启动上游 |
| uv / PostgreSQL | 环境管理、运行状态和产品数据 | pyproject、迁移、Compose、初始化 | PG 服务未运行；单测用显式 SQLite |
| LangGraph | 结构化需求规划与校验循环 | 实际图节点与条件边代码 | 依赖缺失，对应测试跳过 |
| Temporal | 跨阶段持久编排、审批等待、重试 | SDK workflow/activity/worker/outbox | 服务与 SDK 未运行 |
| OpenSpec | 规格与变更文档、CLI 验证 | 文档生成与真实 CLI 门禁命令 | 文档生成通过；CLI 未执行 |
| LiteLLM | 模型网关 | HTTP 适配器、网关配置、Ollama 配置脚本 | HTTP mock 契约通过；未调用真实模型 |
| ToolHive | MCP 启动、代理、工具过滤 | 镜像/准备/启动脚本、部署说明 | 未启动 |
| Serena | 模板符号上下文 | MCP initialize/list/call 读取适配器 | 未调用真实 LSP |
| diagrams | 技术部署图 | 可信 Python 渲染函数与导出源文件 | 缺依赖未运行；ER 使用 dot 已运行 |
| Structurizr / C4 | 系统、容器、组件图 | 平台/产品 DSL、新版 validate/export helper | DSL 源生成；解析未执行 |
| Coder | 可持久人工 IDE | REST 创建工作区、单管理员门禁 | HTTP mock 通过；无实际服务 |
| CubeSandbox | 临时 MicroVM 验证器 | E2B 创建、文件上传、固定命令、回收 | 无实际 KVM/Cube 环境 |
| OpenHands | 下一阶段自由编码候选 | 独立隔离探针与扩展说明 | 未接主链路、未运行 |

这里“集成”分为主链路代码、外部适配器和独立扩展示例三个等级，不把仅有配置或 API wrapper 写成已经全链路接通。

## 5. 一次运行的数据流

用户创建项目时，保存名称、模板 ID 和第一条消息。以后补充消息只追加到项目聊天记录。启动 run 时，服务器把当时的消息列表冻结到 `rnd_run.request`，并在同一个数据库事务中写入 start outbox。这避免“记录保存了但任务没有可靠提交”的丢单窗口。

dispatcher 从 outbox 取任务，以 run UUID 作为工作流稳定身份提交 Temporal。重复提交不应启动第二个相同工作流；接口还用 owner + idempotency_key 限制重试重复创建。outbox 重试优先照顾尝试次数少的项目，避免单条异常长期堵住后续提交。

plan activity 调用 LangGraph：demo 给出固定规格，litellm 调用真实网关，可选先通过 ToolHive/Serena 获取固定模板符号概览。模型返回纯 JSON，由 Pydantic 检查字段、类型、重复名、保留字、外键存在性和无环约束。结构化规格通过后保存 digest，等待人工批准。

批准请求必须包含同一个 digest，所有权必须匹配，未支持项存在时还需要 accept_limitations。该决定经第二类 outbox 发送为 Temporal signal。浏览器断开不会立即丢弃该工作流；但能否恢复依赖 Temporal 持久数据与 worker 正确配置，不能仅凭网页显示“运行中”推断成功。

generate activity 从干净上游复制并追加业务运行时、schema、Vue 入口、Alembic 迁移、独立 Compose、文档与图。规范在此生成 OpenSpec change 文档；**当前批准对象是 canonical ProjectSpec JSON，不是用户可以任意改写并执行的 OpenSpec Markdown**。

verify activity 检查源码、业务契约、OpenSpec CLI，以及所选的额外 sandbox 检查。package activity 只有收到报告才能打 ZIP，排除密钥、缓存、依赖和符号链接，计算文件清单和整体 SHA，再标记 READY。下载接口再次核对归属和 SHA。

## 6. 哪些数据是真实来源

| 对象 | 当前事实来源 | 不应混淆为 |
|---|---|---|
| 原始需求 | 项目消息 + run 冻结快照 | 模型事后解释 |
| 已批准业务规格 | run.spec + digest、交付 approved-spec.json | 可执行 Markdown 指令 |
| 流程持久事件 | Temporal 工作流历史 | 浏览器轮询状态 |
| 平台展示状态 | PostgreSQL rnd_run/rnd_event | Temporal 每个底层事件的完整替代 |
| 模板版本 | 固定 Git SHA + manifest/receipt | 一直变化的 master |
| 交付源代码 | run/product 目录和 ZIP 的文件 SHA | 聊天里“已完成”一句话 |
| 业务数据 | 产品自己的 PostgreSQL | 平台 rnd_project 或模型上下文 |
| ER 图 | 已批准业务 metadata 的 biz_ 表结构 | 线上数据库反射、上游全部管理表 |

Temporal 开发服务为轻量起步使用持久化 SQLite 文件；**这不替代平台和产品使用 PostgreSQL**。如果要求 Temporal 本身也必须 PostgreSQL 持久化，按官方 server 部署改为专用 Temporal PostgreSQL 数据库和 schema 管理，不能把 CLI start-dev 的文件参数写成 PG URL。[S04]

## 7. 目录导航

```text
ai-rnd-foundation/
  factory/                    原创平台代码
    api.py repository.py      HTTP、归属检查、事务
    workflows.py activities.py Temporal 跨阶段流程
    planner.py providers/     LangGraph 与外部服务适配
    generator.py              模板装配与业务源码生成
    product_runtime.py        被复制进产品的可信 CRUD 运行时
    artifacts.py              OpenSpec、C4、ER、diagrams
    validation.py packaging.py 门禁和安全打包
  templates/fastapiadmin/      模板清单、架构规则
  overlays/platform/          研发平台 Vue 界面
  overlays/product/           生成产品 Vue、启动及容器文件
  migrations/                 平台 rnd_ 数据表迁移
  scripts/                    首次组装、启动、探针、验收
  integrations/               每个外部工具的接入配方
  tests/ reports/             测试与明确范围的证据
  docs/ architecture/         完整手册与架构源文件
  .vendor/                    首次运行后下载的干净上游
  runtime/                    首次组装后的平台及联合环境
  data/runs/<uuid>/           运行产物（本机生成，不进 Git）
```

`.vendor` 不直接二次开发；修改原创 `factory` 或 `overlays`，重新组装 runtime。否则下一次模板复制时会混入不受追踪的修改。生产升级必须记录 overlay 版本，不能只记录上游 SHA。

## 8. 首版的可用功能与明确不足

可以表达普通台账、资产、分类、父子记录，支持文本、整数、有限浮点、布尔、日期、时间及引用；后端包含搜索分页、字段校验、归属检查和父记录删除限制；前端动态构建表单和列表。一个模型规格最多 8 个实体、每实体 16 个字段；限制可调整，但扩大上限前先评估 UI、复杂度和测试成本。

没有自动完成唯一约束、富业务规则、精确货币 Decimal、库存交易、流程审批、权限矩阵、文件上传、消息推送、设备实时采集、复杂报表、多人协作、自助租户和费用系统。产品业务表的 owner_id 隔离也不是完整多租户/RLS 方案。

生成器只创建新项目。对已上线产品增量修改，必须先检查现有数据库与迁移历史，生成新 migration，保留数据与版本；不能在已部署项目重写初始迁移。

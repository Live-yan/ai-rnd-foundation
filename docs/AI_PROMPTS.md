# 可以直接交给编程 AI 的任务提示词

使用方法：先在 VS Code/IDEA 中打开本项目，让编程 AI 能读取源码。每次只交一项任务；要求它先列出准备修改的文件，再实现、执行测试并报告真实结果。把 `<占位符>` 换成你的实际信息。不要把 `.env` 或个人 access token 发给 AI。任何“已完成”都必须有你可重跑的命令和结果。

## P01：首次构建报错，不允许偷偷更换技术栈

```text
你正在修改 ai-rnd-foundation 0.1.0。请先阅读 README.md、docs/START_HERE.md、
docs/VALIDATION_REPORT.md、Dockerfile、scripts/bootstrap.py、scripts/resolve_host.py。
目标是修复下面真实构建错误，并保持 FastapiAdmin 固定提交、uv、PostgreSQL、Vue3、
LangGraph 和 Temporal 的既有职责。

错误日志：<粘贴去掉密钥后的日志>
复现命令：<命令>
操作系统：<Windows WSL/具体Linux版本>

约束：不得替换成另一个 FastAPI 模板；不得删 vue-tsc、OpenSpec 门禁、鉴权或测试；
不得把线上 PostgreSQL 改为 SQLite；不得把失败默认为 demo 成功；不得修改 .env 里的密钥。
先判断错误来自网络、上游依赖、overlay、Docker、迁移还是业务运行时。
只修改必要文件，增加能捕捉此问题的回归测试。不能运行的环境项请明确记为 not_run。
交付：修改清单、原因、补丁、重跑命令、真实结果、仍未验证项。
```

## P02：把硬编码模板拆成可扩展 registry

```text
先阅读 templates/fastapiadmin/manifest.json、ARCHITECTURE.md、factory/api.py、
repository.py、generator.py、activities.py、validation.py 和 tests/。
把唯一模板选择重构为 TemplateRegistry + TemplateAdapter，但保留现有模板行为和API兼容。

需要覆盖：能力校验、固定提交物化、架构输出、可信验证计划、启动说明、adapter版本。
不能让模板清单里的任意字符串直接变成 shell 命令；执行器只接收登记的命令类型和参数。
run必须保存template_id、模板SHA和adapter版本快照。旧run必须仍可追溯旧版本。
未知模板返回422，未通过验收的模板只可标记experimental，不允许伪装available。

先让原有 FastapiAdmin 测试全部通过，再增加一个测试用虚拟adapter验证分发机制。
虚拟adapter只能在tests中使用，不出现在用户可选模板里。
不要同时实现Java业务生成；本任务只完成真实扩展协议和回归测试。
```

## P03：添加 Spring Boot + Vue 的 Golden Template

```text
在已经完成TemplateRegistry的基础上增加 springboot-vue-pg-v1。
我已人工验收的仓库是 <仓库URL>，固定提交 <SHA>，Java版本 <版本>，构建工具 <Maven/Gradle>。
先读取该模板的启动、鉴权、目录、迁移、前端路由及测试，不凭记忆猜接口。

生成输入仍是经过审批的ProjectSpec，业务范围先限制为CRUD+无环父子关联。
输出必须包括Java实体/DTO/Repository/Service/Controller、Vue页面、PG迁移、
C4 DSL、ER图和数据字典、独立启动说明。保留原模板许可证和身份认证。
未知或不支持的字段/能力应明确拒绝，不静默丢弃。

验收：后端编译和测试、真实PostgreSQL迁移、Vue类型/构建、两用户数据归属、
错误外键、父子删除约束、干净目录启动下载ZIP。不能用Python模板的测试冒充Java验收。
分小步提交，提供每一步的命令与证据，所有未运行项写not_run。
```

## P04：为 FastapiAdmin 添加唯一编码

```text
阅读factory/schemas.py、product_runtime.py、generator.py、artifacts.py及业务测试。
给FieldSpec增加明确的唯一约束能力，默认唯一范围为(owner_id, field)，而非全局唯一。
同时实现Pydantic schema、PG UniqueConstraint、冻结迁移、重复错误409、Vue提示、
OpenSpec和数据字典输出、模型能力提示。不要只做前端检查。

测试必须包含：同owner重复失败，不同owner可用相同编码，更新为重复值失败，
nullable unique语义，真实PG行为，迁移后约束存在。
给已上线项目生成新迁移，不能重写已执行0001或要求用户删库。
```

## P05：给真实模型规划增加质量评测

```text
阅读factory/providers/llm.py、planner.py、schemas.py。建立不含敏感数据的evals需求集：
资产、图书、货架、巡检、客户台账等至少10组，每组记录期望实体、关键字段与不支持项。
加入恶意需求：要求读取.env、执行shell、跳过审批、更换模板、伪造质量报告。

评测检查JSON/schema有效性、领域覆盖、未支持项召回、是否混入固定demo、调用次数和耗时。
不要求自然语言完全逐字一致。HTTP失败不得转换demo。真实模型评测需显式开关与预算；
默认CI只运行不收费的契约测试。输出带模型版本、模板SHA、提示词版本和真实结果的报告。
不得因为一个模型给出“看起来正确”的JSON就宣称任意需求可完成。
```

## P06：将 OpenHands 加入为可选代码修改 activity

```text
先读docs/EXTENDING.md、integrations/openhands/、workflows.py和activities.py。
目标是在独立sandbox中完成一个已批准小任务，不允许在控制面工作目录直接运行agent。
采用核验后的兼容OpenHands SDK/tools/workspace版本和agent-server不可变镜像。

新增CoderProvider协议，输入包括spec_digest、任务、上下文、write_allowlist、预算和超时；
输出包括diff、命令记录、测试证据和未完成项。禁止改鉴权、策略、CI门禁、已有迁移和密钥。
Agent可以运行工作区测试，但最终Verifier使用只读独立环境及固定测试计划。
最多1次repair，迭代次数和费用有上限，超过上限标失败，不无界重试。

为Temporal实现幂等资源ID、heartbeat、取消/超时回收、重启后的连接或清理。
必须真正导出修改后的代码再进入原有package阶段。不能把Conversation结束当作测试通过。
先做一个单模块用例并给证据，不同时开发并行多Agent和自动合并。
```

## P07：真实连接 ToolHive / Serena

```text
阅读integrations/toolhive/和factory/providers/mcp.py。检查当前安装版本帮助及官方文档。
目标是在不暴露未认证公网服务的条件下，从worker完成MCP initialize/list_tools/只读符号读取。
固定一个模板副本；模板根只读，缓存分离；不要挂载Home、平台data、.env或docker.sock。
服务端和客户端都只允许登记的只读工具。

先验证主机连通，再验证worker容器到代理连通，明确每个host/port是谁的地址。
若loopback不可达，给出私网/防火墙/认证代理方案，不能直接改成0.0.0.0无认证。
报告实际返回的工具名、目标文件路径和索引结果；配置存在不代表healthy。
为下一阶段每项目独立实例写设计，但不要现在共享一个可切换活动项目的实例给多用户。
```

## P08：完善 CubeSandbox 执行器

```text
先阅读integrations/cube/、factory/providers/sandbox.py和Cube当前官方E2B兼容示例。
我已有的受控服务：API地址 <私网地址>，template id <ID>，密钥由环境变量提供，不进入提示词。
先用固定无害命令验证创建、文件上传、stdout/stderr/exit_code和退出销毁。

补充实例幂等映射、超时/取消回收、资源限制、文件大小与压缩炸弹防护、
公网和内网出站策略、拒绝访问metadata/平台PG/Redis。不可verify=False。
若要验证整个产品，需要独立PG/Redis和完整依赖环境，不得把AST检查命名为fullstack。
请分别输出控制面、数据面、TLS、模板和隔离测试证据；无KVM环境时明确未运行。
```

## P09：Coder 自动导入源码，保持用户隔离

```text
阅读factory/providers/coder.py、api.py的/coder接口和integrations/coder/README.md。
当前只允许单个显式管理员创建workspace，ZIP导入是手工的。请实现安全的自动导入步骤。

先设计平台用户与Coder身份绑定，不允许所有租户共用一个全权token。
workspace创建、build成功、agent在线、文件传输、SHA验证必须分阶段且幂等。
使用仅对一个artifact有效、短期、可撤销的下载凭据，不传平台登录token或数据库密码。
只解压到/workspace/<project>，拒绝路径穿越和符号链接；原有目录有改动时不覆盖。

提供双用户越权测试、过期凭据、重复请求、断线重试、工作区删除后资源回收测试。
工作区仅创建成功不能标记source_imported或product_ready。
```

## P10：真正的 PostgreSQL + 浏览器端验收

```text
请阅读现有reports和tests，注意现有业务测试使用显式SQLite测试库，不代表PG验收。
增加一个独立集成测试环境，启动真实PG、Redis、固定上游API和Vue构建产物。
用两个真实登录用户操作生成产品：新增父子、列表/搜索/分页、编辑、删除约束、
跨用户读写/引用拒绝、刷新持久化、重启持久化。

使用当前可用的Playwright或等效浏览器工具，版本锁定；处理上游登录验证码要采用
明确测试配置/测试账号流程，不在生产代码中绕过鉴权。不要依靠硬编码Bearer测试身份。
保存真实日志、截图、迁移版本和失败报告；失败时CI必须失败。
最后从平台下载ZIP，在全新目录/空数据库运行同样验收，不能只测生成前的工作目录。
```

## P11：架构图、ER 图与代码一致性

```text
检查factory/artifacts.py、product_runtime.py与generator.py。
使用当前Structurizr统一validate/export命令，不引入已停止维护的Lite/旧CLI为默认方案。
对C1/C2/C3 DSL做真实解析，验证容器、组件关系与产品实际进程/代码一致。
ER从业务metadata生成；若新增真库反射，结果必须标注数据库、采集时间和schema范围。

测试包括中文/引号/换行标签、非法DSL include、主外键、可选引用与索引、
不存在的关系、长标识符、业务表与上游管理表边界。
输出可编辑DSL/DOT/JSON及SVG，并注明每个文件的来源，不把LLM绘图当作真库结构。
```

## P12：发布前审计与版本冻结

```text
这是一个尚未通过生产验收的基础工程。请基于完整源码和本机真实部署做审计，
不要只根据README评价安全。重点：鉴权、owner隔离、shared token、文件路径、
ZIP包敏感信息、SSRF、Docker socket、MCP工具权限、sandbox出站、默认账户、
迁移恢复、依赖/镜像漏洞、模型费用和资源配额。

先列风险及复现，再逐项修复并加测试。生成真正运行后的uv.lock、pnpm锁、镜像digest、
模板SHA、overlay版本、SBOM、测试矩阵与备份恢复报告。
不得编造CVEs、扫描结果、性能或通过率。未验证项保留not_run并阻止对应生产发布条件。
```

## AI 修改结果怎样验收

先看是否保持用户当前技术栈和边界；再看 diff 是否只改目标文件；再运行它给出的命令；最后检查新增测试真的覆盖失败用例，而不是空断言。让 AI 输出“执行了哪些测试、哪些没有执行、为什么”，比要求它写“完全完成、非常优雅”更有价值。

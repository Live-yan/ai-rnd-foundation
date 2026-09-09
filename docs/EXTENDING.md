# 如何增加框架、业务能力和 Agent

## 1. 扩展前先理解“模板”不是 Git 链接

一个模板至少是：真实仓库固定提交、明确许可证、可运行起点、目录/依赖规则、配置问题清单、数据库迁移方式、生成器、图表映射、验证器和独立交付说明。缺任何一部分，都不应该出现在面向用户的“已支持”下拉框里。

本版只有 `fastapiadmin-pg-v1`，模板选择虽已显示在界面，后台仍明确限制此 ID。没有预装 Spring Boot、React 或 Go 假模板。下面是实际开发路径，不是已完成能力清单。

## 2. 扩展 FastapiAdmin 业务能力：先小后大

最容易的第一步是增加“字符串唯一编码”。需要同时修改 FieldSpec 的能力声明、Pydantic 校验、SQLAlchemy metadata、冻结迁移、异常映射、UI 错误、ER/数据字典以及测试。必须决定唯一范围：全系统唯一还是 `(owner_id, code)` 联合唯一；两者对业务和多用户意义不同。

实施步骤：先复制现有 tests 增加两个同 owner 重复编码冲突的红测试；再增加另一个 owner 是否允许相同编码的测试；修改 migration renderer 和 runtime；执行 PG 真库验收；最后才让模型在 schema 中输出 unique 字段。只改提示词而没有数据库约束不是完成。

第二步可以将外键 ID 输入换成搜索下拉。新增后端受归属约束的引用候选 API，前端只查询自己可访问的父实体。大表必须有分页，不一次把全部记录拉进浏览器，也不能为了展示下拉而取消所有权限制。

第三步是精确数值。财务金额不应简单用普通 number/float 代表精确小数。新增 decimal 类型，明确 precision、scale、JSON 编码和数据库 Numeric，并加入边界/四舍五入测试。该能力未完成前，支付、结算、财务软件应列为不支持。

## 3. 增加第二套框架：建议 Spring Boot + Vue

这是扩展练习，不强制选某个商业框架，也不提供未经核验的第三方仓库冒充可用模板。先选择许可证适合、能在你的电脑独立运行的 Java/Vue Golden Repository，记录 Git SHA。Java 版本、Spring Boot 版本、构建工具、Node 版本全部以该模板实际声明与当前官方要求为准。

阶段 A，人工验证空模板。新目录克隆固定提交，先不接平台，完成数据库配置、后端编译、前端构建、登录和一个手写 CRUD 示例。保存原始日志。若这个步骤不通过，不能把问题推给 Agent。

阶段 B，写架构包。在 `templates/springboot-vue/` 新建 manifest 和 ARCHITECTURE.md，写清 Java 包名、controller/service/repository/entity/DTO 的目录、鉴权扩展点、PG 配置、Maven/Gradle 命令、Flyway/Liquibase 迁移、前端路由以及禁止 AI 修改的文件。

阶段 C，把当前硬编码拆成真实 registry，而不是加一个 JSON 后就结束。建议提供下列协议：

```python
class TemplateAdapter(Protocol):
    id: str
    def validate_capabilities(self, spec: ProjectSpec) -> None: ...
    def materialize(self, spec: ProjectSpec, destination: Path) -> dict: ...
    def verification_plan(self, product: Path) -> list[TrustedCheck]: ...
    def export_architecture(self, spec: ProjectSpec, product: Path) -> dict: ...
```

这是目标接口草案，目前没有在根代码里假装注册未实现的 adapter。`TrustedCheck` 应指管理员登记的固定命令/镜像，不接受用户或模型提供任意 command 字符串。

阶段 D，逐处改动：`factory/api.py` 的模板列表、`repository.py` 的模板校验、`generator.py` 的模板选择、`activities.py` 传递模板 ID、验证器的选择和模型上下文中的能力集。UI 应从 API 取数据，不自行拼接“Java 已支持”。给 run 保存 adapter 版本，旧 run 必须仍可追溯旧 renderer。

阶段 E，实现 Java renderer。把一个已批准实体转换成 Entity、DTO、Repository、Service、Controller、迁移和 Vue 页面。生成代码只从白名单 schema 出发；原始需求中的引号、换行、路径或命令不能进入可执行模板位置。模板字符串本身放 Git 审核。

阶段 F，换成真正的 Java 验证。至少编译、单测、真实 PostgreSQL 集成测试、前端类型与构建、两用户权限、完整 ZIP 在干净目录启动。Java 项目不能调用本版 Python business_runtime 的测试然后声称验收通过。

阶段 G，试点后启用。创建 `template_id=springboot-vue-pg-v1` 的新项目，检查下载包中的 `pom.xml`/Gradle 文件、前端源码、迁移、图和独立说明。只有 CI 和真实运行验收都通过，才把模板状态改为 available。

## 4. 更换前端：Vue → React 或其他方案

前端不是改一个 package.json。为 React 模板准备自己的黄金仓库、鉴权状态管理、API client、表单组件、路由挂载、类型生成、构建及浏览器测试。后端 ProjectSpec 可以共用，但 UI renderer 和前端验证步骤必须不同。保留同一 JSON/OpenAPI 契约有助于隔离变化。

## 5. 增加 Agent 执行器

当前规划器可替换模型，但不执行任意源码编辑。下一阶段把功能分为 Planner、Coder、Verifier、Reviewer，而不是让四个 Agent 都拥有同样的主机 shell 和密钥。

推荐的增加顺序：先对一个单文件改动实验 OpenHands SDK；再用独立 workspace 改一个可信模板模块；再执行完整测试；最后把它作为 Temporal activity 接入。`integrations/openhands/probe.py` 仅是第一个隔离实验。

设计输入：已批准 spec digest、选定任务、最小上下文、只写白名单、固定测试计划、短期模型凭据、预算/超时。设计输出：diff、执行记录、测试证据、未完成项、artifact SHA。不得只返回一个“success=true”。

工作流建议为 plan → 人工批准 → materialize → code → test → 最多一次有预算的 repair → independent verify → package。当前代码没有 code/repair 这两个节点，需要实际新增 activity、状态、错误处理和测试；不要把现有 generate 改成 shell=True 的 Agent 调用。

选择 OpenHands 是针对可嵌入 SDK、远程 Agent Server、工具及工作区分离的工程判断，不是宣称所有任务都优于 Codex、Claude Agent SDK 或 DeepAgents。企业许可证、模型能力、费用、上下文管理和团队熟悉程度都会影响选择。[S11][S12]

## 6. 与 Cube 和 Coder 的关系

自由编码 Agent 应进入独立执行环境。OpenHands DockerWorkspace 支持其自己的 Agent Server 协议；Cube 暴露 E2B 兼容接口。两者的 API 不是一回事，须在 Cube 模板里部署合适的 Agent Server，或编写能处理文件、命令、事件和生命周期的 Workspace adapter。

Coder 在需要人介入时提供持久目录和 IDE。人工修改后的代码回平台，应走明确的 Git commit/diff 或 artifact import，不能后台悄悄覆盖已经批准的 run 目录。当前只创建工作区并指导手工 ZIP 导入；未来自动传输需用户身份映射和短期下载凭据。

## 7. 接 GitHub PR / Actions

先让代码成为受控 Git repository，再增加独立 GitProvider。只给目标仓库所需的 installation token 权限；每 run 创建独立分支；提交前检查没有 `.env`、私钥、数据库备份；PR 描述写原始需求摘要、未支持项、测试范围和 artifact SHA。

CI 验证是独立裁判。Agent 不应能修改发布门禁或伪造测试结果。不要默认自合并；对迁移、权限、支付等敏感变更保留人工批准。本包不自动创建仓库、PR 或合并；`.github/workflows/tests.yml` 只是本基础代码的可执行契约测试工作流，未在你的 GitHub Actions 账户运行。

## 8. 图表怎样扩展才不会与代码脱节

当前 C4 来源于模板架构和业务 schema；ER 来源于相同 business metadata。增加部署组件时更新架构 renderer 和测试，不让 LLM单独画一张与源码无关的漂亮图。

要导出真正数据库 ER，新增 read-only schema reflection adapter：对经授权的测试数据库运行 SQLAlchemy Inspector 或其他工具，导出表、列、PK、FK、索引，再渲染。清楚区分“设计 ER”“迁移后测试库 ER”“生产库 ER”，标注来源、数据库版本与采集时间。不在网页传入任意数据库 URL，防止 SSRF 和数据外泄。

可增加完整 OpenAPI、接口 Markdown、数据字典、迁移 SQL、依赖 SBOM、ADR、测试矩阵和部署手册。每个导出物都注明来源版本，不把没做的验收写成成功。

## 9. 模板升级和已上线项目更新

模板仓库升级新提交之前，在新的分支修改 manifest SHA，先跑 contract check，确认应用工厂、鉴权返回值、Vue 导出路由和目录没有变化。合并一次成功构建产生的真实锁文件与镜像摘要，增加 overlay 兼容测试。保留旧模板版本，旧 run 的产物不可原地替换。

已上线产品更新不是再次生成一个新空 ZIP 覆盖目录。应计算现有版本与新 spec 的差异，生成新的 migration，做备份与恢复演练，保留人工改动，完成兼容性测试。推荐以后引入 Copier 或专用模板升级策略，但本版没有隐式实现三方合并。

## 10. 分阶段完成路线与验收门

| 阶段 | 真正要做的工作 | 达到什么才进入下一阶段 |
|---|---|---|
| M0 | 首次在线构建固定 FastapiAdmin 主机 | 登录、API、Vue、PG、Redis 均在本机成功 |
| M1 | demo 完整控制流与干净产品启动 | 下载、SHA、产品 CRUD、持久化、两用户隔离通过 |
| M2 | 真实 LiteLLM 模型规格规划 | 多组不同需求生成不同正确结构，失败不降级 |
| M3 | OpenSpec/diagrams/C4 导出验收 | CLI 验证、SVG、DSL 解析与业务表一致 |
| M4 | 选用 ToolHive/Serena/Cube/Coder | 每个真实探针和资源回收/归属验收通过 |
| M5 | OpenHands 单任务代码修改 | 隔离、diff 白名单、独立测试、预算和超时通过 |
| M6 | 第二套框架 | 不同 renderer/verifier 的新项目干净启动通过 |
| M7 | 生产化 | 鉴权/租户/审计/限流/备份/恢复/安全审计通过 |

阶段是成果门槛，不是时间承诺。不能用一个工具名字或截图代替实测证据。

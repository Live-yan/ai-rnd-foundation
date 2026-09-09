# 验证报告 · 本次交付范围

## 1. 结论

本基础包包含实际可执行实现和测试，但 **尚未在本次交付环境证明：真实 FastapiAdmin 完整构建、真实 PostgreSQL + Redis + Temporal + LangGraph 工作流、真实模型与全部外部工具联调、下载产品的干净环境启动**。

本次执行环境为 Linux / Python 3.13.5。基础实现按 Python 3.12 容器构建；两者并非同一套已验证依赖环境。容器环境没有可用 Docker daemon、PostgreSQL、LangGraph、Temporal SDK、OpenSpec、diagrams、MCP SDK 及远端工具凭据，且不能直接拉取整个上游仓库或安装完整依赖。没有通过伪造工具、假服务响应或临时禁用生产约束冒充验收。

## 2. 本地实际结果

测试命令：

```bash
python -m pytest --junitxml=reports/junit-local.xml
```

本次结果：**64 passed，1 skipped**。完整输出和JUnit XML保存在reports目录。跳过项是依赖真实LangGraph的demo图执行；它没有被计为通过。

通过范围：标识符/能力schema校验，保留路由冲突，重复字段/无效外键/循环依赖拒绝，CRUD类型、必填、归属和引用约束，API项目归属、幂等、需求冻结、审批hash与限制确认，输出路径与秘密过滤，文件哈希与下载篡改拒绝，LiteLLM/Coder HTTP mock契约。

竖向产物测试使用一个明确标记的 **测试专用最小上游fixture**，执行了真实业务生成、Graphviz ER渲染、源解析、业务契约、ZIP打包和哈希复验。这个测试fixture不能证明真正FastapiAdmin前端/鉴权/数据库初始化可运行，也不作为用户模板发布。生产生成器要求真实固定上游receipt；不会自动退回fixture。

## 3. 其他检查

Python源码编译检查、Compose YAML结构解析、Shell脚本语法检查和两个Vue组件中TypeScript脚本的语法转译另存 `reports/static-checks.json`。YAML解析不是docker compose config实际解析；TS语法转译不是vue-tsc或Vue模板编译；源码存在不是Docker镜像已构建。

C4源文件已生成，但本次未运行Structurizr parser。diagrams Python部署图源已实现，本次未执行其依赖库；本包可见的ER SVG由实际Graphviz生成。文档PDF单独经过渲染检查，这与软件运行验收不同。

## 4. 必须由真实环境补齐的验收矩阵

| 项目 | 当前状态 | 本机应执行的验收 |
|---|---|---|
| 固定上游下载/合同 | 未运行完整下载 | bootstrap获取SHA、contract通过 |
| 上游+overlay前端 | 未运行Vue编译 | pnpm frozen install、vue-tsc、Vite build |
| uv联合依赖解析 | 未运行 | 实际生成锁文件并保存 |
| PG/Redis/上游登录 | 未运行 | 容器健康、初始化、真实账号登录 |
| Temporal完整控制流 | 未运行 | demo提交→审批→READY→下载 |
| LangGraph真实执行 | 本地跳过 | 环境依赖安装后重新运行测试与demo |
| OpenSpec CLI | 未运行 | strict validate成功并保存日志 |
| diagrams | 未运行 | deployment SVG实际产生 |
| Structurizr parser | 未运行 | validate/export实际成功 |
| 真实模型 | 未运行 | 不同真实需求+非法输出/超时场景 |
| ToolHive/Serena | 未运行 | initialize/list/read、作用域/认证验证 |
| Cube | 未运行 | KVM模板、创建/上传/固定检查/销毁 |
| Coder | 未运行 | 身份、template build、IDE和持久化 |
| 干净交付产品 | 未运行 | 新目录Compose、真实PG、双用户浏览器验收 |
| 生产安全/负载/备份恢复 | 未运行 | 独立审计、扫描、配额、实际恢复 |

## 5. 真实控制流验收脚本

在已完成真实上游登录后，取你自己的有效登录token，只在终端临时环境变量传入；不要提交Git或贴到聊天。`FACTORY_LOGIN_TOKEN` 不是 `.env` 中的诊断token。

```bash
# 交互输入，不把token明文写在shell历史中：
read -r -s -p 'Your current login token: ' FACTORY_LOGIN_TOKEN
export FACTORY_LOGIN_TOKEN
printf '\n'
uv run python scripts/smoke_e2e.py --accept-demo
unset FACTORY_LOGIN_TOKEN
```

脚本实际调用创建项目、启动run、等待审批、批准、等待下载并检查SHA。成功结果保存 `reports/live-smoke/`。即便该脚本通过，**仍不表示脚本自动构建了下载产品**；它的报告明确标注 fresh_product_compose 未运行，需按 START_HERE 第6节补测。

## 6. READY 的含义

本版 `READY / scaffold_ready` 表示：在运行环境中执行的指定门禁通过，可以下载源码骨架。它不表示任意用户需求全部满足，也不表示所有外部工具在这一run中都执行。每个run的quality.json应作为判据，不能用页面绿色状态替代完整验收。

## 7. 不做的承诺

本包没有声称是完全离线镜像包、没有声称11个工具均已实机联调、没有声称使用了真实付费模型、没有声称已在你的GitHub创建PR或运行Actions，也没有提供虚构的吞吐、费用、延迟或部署时间。

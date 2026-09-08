# 运行、安全与运维

## 1. 端口与运行角色

| 服务 | 主机本地端口 | 容器内连接方式 | 说明 |
|---|---|---|---|
| 平台 | 8000 | api:8000 | /web/ 与 /factory-api |
| 平台 PG | 55432 | postgres:5432 | rnd_ 和上游管理数据 |
| 平台 Redis | 默认不暴露 | redis:6379 | 上游会话和缓存 |
| Temporal | 7233 / 8233 | temporal:7233 | RPC / 开发 UI，均本地绑定 |
| LiteLLM | 4000 | litellm:4000 | ai profile 才启动 |
| Structurizr local | 8080 | structurizr:8080 | architecture profile |
| 生成产品 | 8010 | app:8010 | 与平台独立运行 |
| 产品 PG/Redis | 55433 / 56380 | postgres:5432 / redis:6379 | 多产品需改端口与项目名 |

容器里的 localhost 是该容器，不是 Windows、WSL 或其他容器。Compose 服务通过服务名连接；浏览器通过主机映射端口访问。Cube 的远端 URL、Coder URL、ToolHive MCP endpoint 又属于另一层，不能把四类地址互换。

## 2. 数据库与迁移

平台表用 `rnd_` 前缀，与上游表分开；产品表用 `biz_` 前缀。平台使用独立 `rnd_alembic_version`，产品使用 `business_alembic_version`。首版依赖上游首次初始化其管理表，新增平台和业务表则有显式迁移；尚未对上游每次升级完成迁移兼容测试。

不要在运行期间 `create_all()` 代替版本化迁移，不要改已部署的 `0001`。新增字段采用新 revision，先在数据库副本执行升级和回滚/恢复测试。不可逆迁移必须明确备份恢复路线。

本版测试的 SQLite 只用于隔离契约；不证明 PostgreSQL 的并发、事务、索引、排序规则和权限全部正确。全栈验收必须实际使用 PG。

## 3. 凭据与身份

登录身份来自真实 FastapiAdmin。新增研发 API 使用 owner_id 检查项目与 run 归属；生成业务数据同样使用服务端身份写 owner_id，而不接受浏览器随意传入。当前没有组织共享项目、细粒度工作流 RBAC、PG RLS 或收费多租户。

不要认为模板自带管理员角色就自动获得新业务的完整权限矩阵。新功能的租户和协作权限需要单独设计。Coder provisioning 当前故意只开放给一个配置好的 FastapiAdmin 用户，避免共享服务 token 导致跨用户工作区混用。

平台 `.env`、模型 key、Coder token、Cube key 和 MCP token 不进入生成产品。产品 `init_product.py` 自己产生数据库/Redis/JWT 秘密。对外模型会接收需求文本和可选模板符号上下文；敏感项目必须先确认数据能否外发，并采用脱敏或内部模型。

## 4. Docker socket 是一个高权限入口

默认 worker 没有 Docker socket，static 路线只做源码与可信业务契约测试。需要 Docker sandbox 时先构建验证镜像：

```bash
docker build -t ai-rnd-verifier:0.1.0 -f integrations/cube/Dockerfile.verifier .
# 仅限受信任的本地实验：
docker compose -f compose.yaml -f compose.sandbox.yaml up -d --force-recreate worker
```

额外 override 为了访问宿主 Docker daemon 将 worker 以高权限运行并挂 socket。即使子容器配置只读、无网络、CPU/内存/进程限制，父 worker 一旦被攻破仍可能控制主机 Docker。这不是多租户隔离方案。生产应把执行器放独立机器/受控服务或真正的 Cube MicroVM，并移除控制面的 Docker 权限。

## 5. 流程可靠性与限制

提交使用事务 outbox；执行 ID 和 API 幂等键避免重复任务；审批匹配 spec digest；生成使用文件锁和 staging 原子替换；打包使用原子写入与哈希；生成和打包可有限重试。模型规划 activity 不做无界重试，内部只对 schema 校验失败最多再尝试一次。

当前没有用户取消 API、全局费用预算、每用户并发配额、任务清理 API、复杂补偿和工作流版本迁移机制。不要把 Temporal 组件本身的能力等同于平台已实现这些产品功能。新增长时间自由编码时，需要 heartbeat、取消传播、幂等外部资源 ID 和回收记录。

如果 worker 停止，API 仍可能健康，任务会在 QUEUED 等待。Temporal 的 local dev 持久卷被删除后无法靠平台状态表恢复完整事件历史。保留日志、outbox、数据库和 Temporal 数据，分析一致性后再恢复，不随意手工把 run.status 改成 READY。

## 6. 本地备份示例

在平台根目录操作；备份文件含业务和用户信息，放到受控目录，不提交 Git。

```bash
mkdir -p private-backups
chmod 700 private-backups
docker compose exec -T postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U factory -d factory -Fc' > private-backups/factory.dump
```

备份 ZIP/产物还需要 `data/`；凭据需单独加密保管。Temporal dev SQLite 在服务停止后备份所在卷，或使用一致性备份方法，不在高写入时直接复制一个不一致的数据库文件。不要把简单 tar 与 PG dump 当成已经完成灾备。

恢复演练要在新 Compose 项目、空数据库和不同端口做，先确认目标不是现有生产数据库。检查能否登录、旧 run 能否下载且 SHA 一致、产品业务记录和关系是否还在。只有实际恢复成功才叫备份可用。

## 7. 生产上线阻塞清单

正式公开服务之前，必须完成：TLS/反向代理、默认账号替换、权限与租户模型、每用户配额、密钥管理、网络出站控制、审计留存、依赖/镜像扫描、真实 PG 和浏览器端测试、产物与数据备份恢复、事件告警和资源回收。

模板现有其他模块（上游定时任务、文件、AI、聊天等）也应纳入审计，不能只审新增 factory 目录。单实例限制和上游模块开关要按当前固定提交文档评估，不能盲目加多个 API 副本而破坏内存连接或定时任务行为。[S01]

用户需求、外部文档和 MCP 结果一律视为不可信输入。模型可提出规格，不能解除安全策略、修改执行镜像、改变下载路径、读取 .env 或写测试报告。静态约束缩小风险，不是完整形式化安全证明。

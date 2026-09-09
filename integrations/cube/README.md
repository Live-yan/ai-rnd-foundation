# CubeSandbox：远端 KVM MicroVM 执行适配器

本包通过 `e2b-code-interpreter` SDK 实现 `Sandbox.create`、上传交付 ZIP、固定命令检查、结果回传和 context manager 清理。当前用途是 **source verification**，不是完整 FastapiAdmin + PostgreSQL + Redis + 浏览器测试，也没有自由编码 Agent 自动驻留 Cube 的实现。

## 运行条件

你需要可运行 KVM 的 Linux 环境，验证 `/dev/kvm` 可用，并按官方 CubeSandbox 文档部署 CubeAPI、控制面、Cubelet、数据面及模板。Windows + AMD CPU 不自动等于 WSL/Docker 内已有可用 KVM。可以把平台放 Windows WSL，把 Cube 放私有 Linux 服务器；默认小规模流程不需要 Kubernetes，也不强制安装 Cube。

Cube 官方 quickstart 使用 `E2B_API_URL`（例如私网节点 3000 端口），不是把普通公网域名随意塞入 SDK 的 domain 参数。平台设置：

```dotenv
FACTORY_CUBE_API_URL=https://your-private-cube-api.example
FACTORY_CUBE_API_KEY=REPLACE_WITH_A_REAL_KEY
FACTORY_CUBE_TEMPLATE=REPLACE_WITH_A_VERIFIED_TEMPLATE_ID
```

HTTP 仅限受信任隔离私网测试；正式连接使用有效 TLS 证书。不要 `verify=False` 跳过校验。若使用内部 CA，应把该 CA 加入信任链。

## 模板必须具备什么

官方 sandbox-code 镜像提供 Cube 所需 agent/envd；模板中还应有 Python、可写 `/home/user` 和足够磁盘。平台提交的是 stdlib 源码检查任务，所以不依赖安装业务项目的所有依赖。`Dockerfile.verifier` 是 **Docker 验证器镜像**，不能直接当成一个具备 Cube agent/envd 的官方 MicroVM 模板。

官方模板创建命令见 S06；镜像先在你的环境验证并锁定 tag/digest，记录 template ID。不要自动使用教程里的 `latest` 作为生产固定版本。

```bash
docker compose exec worker python scripts/probe_integrations.py cube
```

此探针会实际创建临时 sandbox、执行固定的 Python 版本检查并销毁，会消耗你的 Cube 资源。确认 endpoint、配额和模板后再运行。随后在 UI 选择 cube 验证一个示例产物，查看质量报告中的 cube 结果。

## 隔离并非一句 allow_internet_access=False

适配器禁用公网出站、设置超时并在退出时回收；但公网出站禁用不等于所有内网资产都不可达。Cube 管理员还应限制私网网段、平台 PG/Redis/metadata 地址和文件大小，设置资源/数量配额。未通过这些隔离验收前，不把它开放给不可信租户。

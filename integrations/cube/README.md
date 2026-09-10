# CubeSandbox：隔离执行与完整产品验收

当前版本区分基础模式的 `source_only` 和完整模式的 `generated_crud_stack`。完整模式不接受仅源码检查冒充全栈验收。

模板镜像配方为 `Dockerfile.fullstack`，保留官方 Cube 基座的 envd/agent，预装固定验收器、Python 依赖和前端缓存、PostgreSQL/Redis。构建步骤见 `docs/FINAL_CONSTRAINTS.md`；详细网络与工具配置见 `docs/INTEGRATION_ACCEPTANCE.md`。`Dockerfile.verifier` 是普通 Docker 源码检查镜像，不能当成完整 Cube MicroVM 模板。

你需要实际 Linux/KVM、可用 Cube 控制面和已导入模板。Windows/WSL/Docker 能启动平台不代表 `/dev/kvm` 或 Cube 模板已可用。平台可以在 WSL，Cube 服务部署到受控 Linux 服务器。建议全栈模板至少 6 GiB 内存。

在工具链 Cube 卡片填写实际 API URL、API Key 和 Template ID，或设置同名 `FACTORY_CUBE_*` 环境默认值。不得使用伪造模板 ID、跳过 TLS 校验或把 E2B 公有服务默认当成你的 Cube。

适配器上传本次源码 ZIP，在沙箱中以非 root 的 factory 用户执行镜像内固定验收命令。验收器创建自己的临时 PG/Redis、构建/类型检查前端，验证原生 FastapiAdmin 登录及用户归属隔离，返回与上传 ZIP SHA-256 绑定的报告。完成后 context manager 回收沙箱；失败不回退到宿主机执行。

外网关闭不等于全部内网隔离。部署者还需禁止沙箱访问云元数据、平台数据库、管理端口，设置实例/时间/费用上限。真实集群模板注册、SDK 兼容、网络、资源回收和配额须在你的环境验收。CI 中相同验收器在一次性容器通过，不代表你的外部 MicroVM 已运行成功。

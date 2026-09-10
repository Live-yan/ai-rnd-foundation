# Coder：创建工作区并自动导入本次源码

这里是**真实 Coder Terraform 模板**，不是一个指向空 IDE 的链接。平台完整模式在 ZIP 生成后调用 Coder API，传入限时源码能力凭证，等待 `latest_build.status=running`、Agent `connected` 和 `rnd_source_sha256` 元数据等于交付包 SHA-256，才结束该阶段。

## 1. 前置条件

已有可访问的 Coder 服务及具备模板管理权限的账号，已安装与服务兼容的 Coder CLI。Coder 部署、首次管理员创建、许可证/资源配额按官方文档处理。这里不会替你创建云资源或开放公网服务。

在 Coder Docker provisioner 使用的 Docker daemon 上构建镜像：

```bash
docker build -t ai-rnd-coder:0.2.0 integrations/coder
```

Docker daemon 是运行工作区容器的那一个，不一定是运行研发平台的机器。镜像必须存在于该 daemon，或推送到它能拉取的私有镜像仓库。部署时将 `workspace_image` 设置为验证后的 image digest。

镜像已提供 Python 3.12、uv、Node 22、npm、pnpm 9.15.3、Git 和源码导入器，以非 root 的 coder 用户运行；不用再依赖通用示例镜像里偶然存在的开发工具。工作区没有 Docker daemon/socket。需要调试产品时按导出包说明连接产品专属 PostgreSQL/Redis（不要复用平台数据库和密钥），然后执行 uv/pnpm 命令；也可把 ZIP 下载到本机用其 Docker Compose 启动。

## 2. 注册模板

```bash
coder login https://你的-coder-服务
coder templates push ai-rnd-product --directory integrations/coder
```

配置 Terraform 变量 `workspace_image`、`network_name` 和 `coder_agent_url`。示例网络 `ai-rnd_default` 只适用于同一 Docker daemon 的本地 Compose 安装。远程 Coder 应使用管理员规划的私有网络/HTTPS 路由。

模板依赖官方 `coder/coder`、`kreuzwerker/docker` providers 及 code-server module。首次推送需要下载依赖；运行 `terraform init` 后保留本地生成的 `.terraform.lock.hcl`。本仓库不伪造 provider lock 或已解析的镜像 digest。

记录 **template ID**，不是 workspace ID；填写平台 `.env`：

```dotenv
FACTORY_CODER_URL=https://你的-coder-服务
FACTORY_CODER_TOKEN=由管理员保管的Coder会话令牌
FACTORY_CODER_TEMPLATE_ID=模板UUID
FACTORY_CODER_OWNER_ID=允许发起完整流水线的FastapiAdmin用户ID
FACTORY_CODER_AUTO_IMPORT=True
FACTORY_CODER_FACTORY_URL=http://api:8000
FACTORY_CODER_IMPORT_TIMEOUT=240
```

`FACTORY_CODER_FACTORY_URL` 是 **Coder 工作区能访问到的平台服务根地址**。同一私有 Compose 网络可用 `http://api:8000`；远程工作区使用平台实际 HTTPS 地址，可包含 `/api/v1` 前缀。平台会追加 `/factory/transfer/<run-id>`。

**不要填写工作区自身的 localhost。** Coder Agent 使用模板 `coder_agent_url`，同一私有网络默认 `http://coder:7080`；远程环境要填写 Agent 可达的 HTTPS 地址。`CODER_ACCESS_URL` 则是浏览器的公开地址，本机为 `http://localhost:7080`。两者不会再通过字符串替换混用。先在相同网络条件的容器内验证 DNS、端口和 TLS。

```bash
docker compose up -d --force-recreate api worker
```

## 3. 运行与状态

在工作台选择完整模式，批准规格后，平台依次执行生成、检查、打包、Coder。使用本模板时，源码自动进入 `/home/coder/project`，code-server 默认打开该目录。

首次下载使用最多 15 分钟的能力凭证，仅能读取指定 run 的指定 SHA-256 ZIP，不能列项目、调用模型或修改运行。它不是平台 JWT、模型 API Key 或 Coder Session Token。Terraform 的 parameter 不是密钥保险库；即使参数标为 ephemeral，仍需保护 Coder 状态和管理员访问权限。这里因此只传短期、只读、单产物凭证。

`import_source.py` 会校验压缩包哈希、限制体积/展开大小、拒绝目录穿越/符号链接/重复项，先写暂存目录再发布。已有不同源码或开发修改不会被覆盖；已成功导入的工作区重启不要求原凭证仍有效。

Coder 创建使用确定性名称，丢失 HTTP 应答后的重试先查找同名工作区，并检查模板和导入哈希。不要手动创建同名工作区，也不要让多个模板向同一目录写入。

只有真实导入回执才返回 `source_import=sha256_verified`。兼容 API `/runs/<id>/coder` 单独调用仍只创建手动导入工作区，不算完整模式成功。

## 4. 明确边界

本模板不把 Docker socket 挂进开发工作区。Coder provisioner 自身运行 Terraform、管理 Docker，依然是高权限管理组件，应与不可信租户和公网访问隔离。

导入成功不等于所有业务已经验收。不可变 ZIP 内的 `delivery/quality.json` 记录打包前检查；打包后的 Coder 回执保存在平台运行详情/`smoke_workbench.py` 的 `run-receipt.json`，不重新改包，以免哈希发生变化。

官方依据：Coder REST workspace API、官方 Docker template、官方 code-server module、Terraform coder_parameter 文档。它们的格式在本次开发时核对过；真正的服务器/模板/网络联调需要你的部署凭据，本地 mock 合同测试不等于已完成该联调。

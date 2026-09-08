# Coder：长期 IDE 工作区，不是生成流水线的危险代码沙箱

本包已实现真实 REST 创建工作区适配器：`factory/providers/coder.py`。需要你已部署的 Coder、有效 API token、已验证的 template ID。平台不会自动部署 Coder，不会替你创建管理员，不会自动配置 Docker provisioner，也不会自动把 ZIP 上传到工作区。

## 配置与验收

先按官方 Docker 安装文档部署独立 Coder（手册 S07）。Coder 使用自己的数据库和生命周期，不能把平台的 `factory` 数据库当成 Coder schema。先在 Coder 界面手工创建并打开一个可用模板：可以是 Linux Docker workspace，也可以是你已有的虚拟机模板。其持久卷必须只属于这个工作区。

在平台 `.env` 配置：

```dotenv
FACTORY_CODER_URL=https://your-private-coder.example
FACTORY_CODER_TOKEN=REPLACE_WITH_A_SCOPED_TOKEN
FACTORY_CODER_TEMPLATE_ID=REPLACE_WITH_A_VERIFIED_TEMPLATE_UUID
FACTORY_CODER_OWNER_ID=REPLACE_WITH_YOUR_FASTAPIADMIN_USER_ID
```

`FACTORY_CODER_OWNER_ID` 是 **FastapiAdmin 中的用户 ID**，不是 Coder 用户 UUID。只允许这名明确指定的管理员使用当前共享 Coder token。否则所有平台用户会在同一个 Coder 账号下创建资源，这是本包主动禁止的行为。

```bash
docker compose up -d --force-recreate api worker
docker compose exec api python scripts/probe_integrations.py coder
```

探针只 GET 当前用户，验证身份，不创建资源。完成一个 READY 项目后，点击“创建 Coder 工作区”，适配器实际 POST `/api/v2/users/me/workspaces`。服务接受请求不等于工作区构建成功，要在 Coder 检查 build 日志和最终状态。重复点击同名工作区可能得到冲突，请在 Coder 找到已创建工作区，不要无限重复创建。

下载平台交付 ZIP，在 Coder 浏览器 IDE 中手工上传、解压，按 `README_DELIVERY.md` 启动。初次验收必须在工作区关闭后重新打开，确认源代码和数据库是否按你选择的模板持久化。

## 后续自动导入

新增专用 artifact transfer adapter：凭用户绑定的 Coder 身份、一次性短期下载凭证和项目 SHA，在指定工作区只写 `/workspace/<project>`。不能把平台全权 token、宿主 Docker socket、平台数据库密码放进工作区。当前实现不包含这段自动传输；扩展提示词见手册。

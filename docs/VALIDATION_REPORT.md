# 当前交付门禁与证据说明

本页定义当前版本的验收方法，**不是随分支滚动更新的“已通过”声明**。每次交付必须绑定同一 Git 提交和同一次 Actions；以该运行的 `verified-delivery` 制品和 `DELIVERY.json` 为准。早期 `reports/junit-local.xml`、64 项本地测试等记录仅属于初始版本，不再作为新版交付依据。

## 1. 三项整改如何关闭

| 待完成项 | 实现与防回归 | 必须取得的证据 |
|---|---|---|
| 页面挂载与配置操作 | Vite 原生依赖解析；实际 Vue 组件嵌入宿主布局；供应商切换清除凭据；关闭授权/切换工具不接收迟到响应 | 三页、四视口共 12 张截图；配置交互通过；diagnostics.json 无错误 |
| 恢复默认与版本一致性 | 数据库 compare-and-swap；重置清除覆盖值而不删除版本行；取消确认不发请求；过期与并发请求返回 409 | JUnit 无失败/跳过，包含真实 PostgreSQL 与 SQLite 的保存/重置/并发测试；浏览器确认、取消、重置后保存通过 |
| 核心栈与工具镜像 | 原生平台登录、需求澄清、版本门禁、审批、生成、下载；独立产品全栈；实际 Cube 镜像断网验收；Coder 工具与网络检查 | 同一产品 ZIP 哈希的两份全栈回执；镜像构建及非 root 运行回执；Coder/LiteLLM 控制台与私有网络可达 |

原始前端失败是类型检查在 Vite 生成自动导入声明之前运行，并使用旧 `/web/` 路径；不是删掉类型检查来消除错误。当前构建先生成声明，再运行完整 `vue-tsc --noEmit`。

Cube `2026.16` 基座实际使用 Ubuntu 22.04，其 apt 软件源不提供本项目需要的 Python 3.12。验收镜像使用固定 uv 版本支持的独立 Python 3.12 发行构建，安装到所有验收用户可读取的 `/opt/rnd-python`，使用系统 CA 和正常 TLS 验证；不复制需要不同 glibc 的 Debian Python，不修改系统 Python，不添加未经批准的软件源。依赖使用同次宿主构建的冻结锁，镜像完成后禁止自动下载解释器；实际验收以无网络、非 root 用户运行。安装系统依赖时仅对安装命令设置 DEBIAN_FRONTEND=noninteractive 和 TZ=Etc/UTC，避免 tzdata 等包等待交互输入而超时，不改变最终应用的时区配置入口。

## 2. 六个 Actions 作业

`contracts` 校验 Python 合同及真实 PostgreSQL 配置并发，上传 JUnit 和 `git archive HEAD` 的源码。`frontend-smoke` 编译实际前端、执行类型检查和浏览器回归。`core-stack` 验证真实 PG/Redis/Temporal/FastapiAdmin、产品认证/归属、实际 C4 parser、Coder/Cube 镜像和控制台。`coder-template` 用 Terraform 验证模板；`c4-contract` 解析英文、中文和特殊字符的真实 DSL。

最后的 `delivery` 依赖以上五项全部成功，再读取**同一次运行**的制品，二次核对测试、交互、回执、源码提交与产品哈希。任一失败、跳过、缺失或哈希不一致，都不会发布 `verified-delivery`。运行中、取消或只通过部分作业不算交付成功。

镜像日志由 `scripts/ci_capture.py` 保存，控制台仅显示末尾；非零退出码和超时仍然失败。此工具只用于经过审阅的不含秘密的构建命令，不用于转储 `.env`、用户请求或运行目录。

## 3. 交付制品

`verified-delivery` 包括：

- `ai-rnd-foundation-source.zip`：被测源码，以及同次镜像实际使用的 `locks/host.uv.lock` 和对应 manifest。压缩包内部生成 `SOURCE_MANIFEST.sha256`；不再复用最初版本失效的哈希清单。
- `ai-rnd-foundation-evidence.zip`：JUnit、页面截图、配置交互、全栈回执、镜像日志、C4 和 Coder 模板锁等证据。
- `DELIVERY.json` 与 `SHA256SUMS`：源码提交、运行地址、动态测试数量、交付范围与各压缩包校验值。

源码提交可能是 GitHub 为 PR 生成的测试合并提交，不应直接冒充分支 HEAD。核对时同时记录 PR HEAD 和被测提交；不能将其他运行的报告拼成“全绿”。源码包需要首次联网构建，不是预装镜像/完全离线安装包。

下载并解压制品后先执行 `sha256sum -c SHA256SUMS`；再解压源码 ZIP，进入其中 `ai-rnd-foundation` 目录执行 `sha256sum -c SOURCE_MANIFEST.sha256`。正常结果应全部为 OK。原始源码 tar 保留在同次 Actions 的 `contract-results` 制品中，用于溯源，不包含本地 `.env`。

## 4. 不能混称通过的层次

CI 的模型 HTTP 是明确标记的测试夹具；LangGraph、LiteLLM SDK、Temporal、数据库、认证、渲染器和产品代码是真实执行。浏览器配置回归使用 API 夹具，不是已完成真实账号登录的截图。

实际 Cube 镜像中的离线产品验收不等于真实 Cube 集群的 KVM、模板注册、envd、SDK 网络均已联调。Coder 模板、工具链和 HTTP 网络可达也不等于你的账号已经成功创建并导入工作区。真实模型授权、ToolHive/Serena 服务和 Coder/Cube 资源仍按 `INTEGRATION_ACCEPTANCE.md` 在部署环境验证。

交付范围是可信单机开发/联调版本和现有 CRUD/关联生成能力；`production_ready=false`。任意复杂业务、跨语言新模板、生产安全/负载/备份恢复不因 CI 变绿自动完成。不要向不可信租户开放带共享 Docker socket 的开发配置。

## 5. 升级保护

升级前备份 `.env`、数据库和 `data/`；保留现有凭据与加密密钥。`init_env.py`、`setup_toolchain.py` 只补必要缺省配置。不要执行 `down -v`、`--fresh` 或 `-Fresh` 来升级。修改 `.env` 后重新创建相关容器，单纯 restart 不会加载新环境值。操作命令以 `START_HERE.md` 为准。

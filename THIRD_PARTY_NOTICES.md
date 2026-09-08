# 第三方项目与版本边界

本压缩包的原创 glue code 使用根目录 MIT LICENSE。FastapiAdmin 本体不在初始压缩包中；首次构建会下载固定提交，生成的平台与产品保留它的原始 LICENSE。不得删除上游版权信息。

FastapiAdmin 固定提交：`f7f5fb61a5c918016640f6b07e053c807381b7cc`。
OpenSpec 安装版本：`1.12.0`；uv 构建工具版本：`0.12.10`。
Structurizr 示例镜像：`2026.06.28-noble`；Temporal CLI 示例：`1.8.3`。

LangGraph、Temporal SDK、diagrams、MCP、E2B SDK 等通过 pyproject 的约束范围实际解析。LiteLLM 的 `main-stable`、PostgreSQL/Redis/Node/Python 的系列镜像标签并非不可变摘要。**没有声称初始包内所有依赖已完全固定或通过供应链扫描。** 首次成功构建后执行 capture_locks.sh，补充镜像 digest、许可证/SBOM/安全扫描，再形成自己的 Golden Release。

Serena 由可选 prepare.sh 首次记录真实 Git SHA；OpenHands 的实验示例需要用户选择兼容 SDK 和不可变 server 镜像。Coder、CubeSandbox、ToolHive 需要独立安装或现有服务。引用资料见 docs/SOURCES.md。商业分发前检查实际使用版本、基础镜像及其传递依赖的许可证；这份声明不是法律审计。

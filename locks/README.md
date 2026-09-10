# Dependency locks

Git 源码仓库默认不提交由初次在线装配产生的宿主组合锁；不是已预装的离线运行环境。
FastapiAdmin 固定源码提交，上游前后端锁随该固定源码一起获取。宿主增加 LangGraph、Temporal 等依赖，通过 `scripts/resolve_host.py` 生成组合 uv 项目。

首次镜像构建实际执行 `uv lock`。五项 CI 验收通过后，交付作业把**同次已测试镜像**中的 `uv.lock` 和 `pyproject.toml` 放入源码 ZIP 的 `locks/host.uv.lock` 与 `locks/host.pyproject.toml`，同时放入证据包。不使用其他运行或旧本地环境的锁冒充当前版本。

使用该交付 ZIP 时，Dockerfile 检测到 `locks/host.uv.lock` 并执行 `uv sync --frozen`。Git checkout 中没有组合锁时仍走首次在线解析；自行部署也可用 `scripts/capture_locks.sh` 留存实际镜像信息。升级依赖必须主动更新锁并重新验收。

镜像 tag 不等于 digest。LiteLLM 的 `main-stable`、Coder 的 `latest` 等是明确的开发用途可变标签，依赖锁不代表所有系统包、基础镜像和外部服务都可完全重现。受控生产部署另行固定验证后的镜像摘要。

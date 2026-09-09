# Dependency locks

本包没有伪造已解析的 uv.lock。受限环境中未完成网络依赖解析。
FastapiAdmin 固定源码提交；上游后端锁与前端锁在拉取后保留。
宿主平台因增加 LangGraph/Temporal 等依赖，使用 scripts/resolve_host.py 生成组合 uv 项目。
第一次镜像构建实际执行 uv lock；构建通过后用 scripts/capture_locks.sh 保存锁与镜像信息。
后续构建检测到 locks/host.uv.lock 时使用 --frozen。升级依赖必须主动更新锁并重新验收。
镜像 tag 不等于 digest。LiteLLM 的 main-stable 明确为可变 tag，不声称可完全重现。

# OpenHands SDK：下一阶段的自由编码执行器候选

当前主链路的 Agent 是 LangGraph 编排的受约束规格规划器；真实模型通过 LiteLLM 接入。代码由确定性模板生成，因而可检查、可限制且无需允许模型执行任意 shell。

OpenHands SDK 适合作为“根据通过审批的任务改代码、运行测试、修复”的扩展候选：其 Agent、Conversation、DockerWorkspace/remote agent server 分工适合平台嵌入。官方 SDK 也有 OpenAI-compatible endpoint 配置。它不是本包已联调的默认生成引擎，也不是 Cube 的 E2B SDK 的直接替代品。要把 OpenHands 接到 Cube，需要真正的 Workspace/Agent Server 传输适配，而不是把 URL 替换一下。

`probe.py` 是 **可执行的独立隔离示例**，不接收平台工作区，不读取平台 .env，不向主业务返回假完成状态。它要求你锁定一组兼容的 SDK/tools/workspace 版本与 agent-server 镜像 digest，并采用一个允许实验的低权限模型 key。建议在专用 Linux 开发机执行，而非直接在生产控制面执行。

```bash
# 在 integrations/openhands 新建独立 uv 环境；版本取你核验过的同一发行组。
uv init --bare --python 3.13
uv add openhands-sdk openhands-tools openhands-workspace
# 首次安装会实际解析版本：检查 lock 与官方 server 兼容性后保存。
# export OPENHANDS_SERVER_IMAGE=ghcr.io/openhands/agent-server@sha256:<verified-digest>
# export LLM_MODEL=<your-compatible-model>
# export LLM_BASE_URL=<gateway-accessible-from-this-runtime>
# export LLM_API_KEY=<short-lived-scoped-key>
uv run python probe.py
```

该示例会真实启动 Docker Agent Server，并让模型执行一个独立临时目录任务，最多 8 次迭代。DockerWorkspace 的基础容器隔离不是多租户安全证明：仍须处理网络、挂载、凭据、资源配额和命令策略。接入主平台前增加 diff 白名单、不可写测试/策略、独立测试裁判、产物导出、超时回收、Temporal 幂等与审批。详见完整手册的扩展路线和提示词。

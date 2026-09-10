from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Literal
from starlette.concurrency import run_in_threadpool
from factory.tool_settings import ToolSettingsService, ToolSettingsInput
from factory.providers.oauth import OAuthService
from factory.providers.export_config import export_config

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header
from fastapi.routing import APIRoute
from fastapi.responses import FileResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text

from factory.config import Settings
from factory.database import Database, Run
from factory.providers.catalog import catalog_payload
from factory.providers.registry import ProviderService
from factory.providers.discover import discover_models
from .crud import Repository
from .schema import (
    ApprovalInput,
    ClarifyInput,
    DiscoverInput,
    MessageInput,
    ProjectInput,
    ProviderInput,
    ProviderUpdate,
    RunInput,
)
from .service import WorkbenchService
from factory.security import file_sha256
from factory.handoff import verify_source_ticket
from factory.toolchain import toolchain_status, RETIRED_TOOLS
from factory.templates import list_templates


def _legacy(request: Request) -> bool:
    return bool(getattr(request.state, "factory_legacy", False))


def create_router(db: Database, settings: Settings, actor_dependency: Callable, *,
                  route_class: type[APIRoute] = APIRoute, response_factory: Callable | None = None, admin_dependency: Callable | None = None) -> APIRouter:
    router = APIRouter(tags=["AI研发平台"])
    core = APIRouter(route_class=route_class)
    repo = Repository(db)
    providers = ProviderService(db, settings)
    service = WorkbenchService(db, settings)
    config_service = ToolSettingsService(db, settings)
    oauth = OAuthService(db, settings)
    is_admin = admin_dependency or (lambda: False)

    def _success(data=None, msg: str = "操作成功", status_code: int = 200):
        # Preserve UTC offsets before the host's display formatter strips them.
        data = jsonable_encoder(data, custom_encoder={
            datetime: lambda d: (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat(),
        })
        if response_factory is not None:
            response = response_factory(data=data, msg=msg, status_code=status_code)
            response.headers["Cache-Control"] = "no-store"
            return response
        return JSONResponse(jsonable_encoder({"code": 0, "msg": msg, "data": data, "success": True}), status_code=status_code, headers={"Cache-Control": "no-store"})

    def _response(request: Request, data=None, msg: str = "操作成功"):
        if _legacy(request):
            return JSONResponse(jsonable_encoder(data), headers={"Cache-Control": "no-store"}, status_code=request.scope["route"].status_code or 200)
        return _success(data, msg, request.scope["route"].status_code or 200)

    @core.get("/health")
    def health(request: Request):
        with db.session() as session:
            session.execute(text("SELECT 1"))
        return _response(request, {"status": "ok", "version": "0.2.0", "scope": "API + database"}, "平台服务正常")

    @core.get("/templates")
    def templates(request: Request, actor: str = Depends(actor_dependency)):
        data = list_templates()
        return _response(request, data, "模板列表获取成功")

    @core.get("/integrations")
    def integrations(request: Request, actor: str = Depends(actor_dependency)):
        rows = toolchain_status(config_service.effective(), sum(1 for item in providers.list(actor) if item["enabled"]))
        if _legacy(request):
            return {row["id"]: ("configured" if row["configured"] else "not_configured") for row in rows}
        return _success(rows, "工具链状态获取成功")

    @core.get("/toolchain")
    def toolchain(request: Request, actor: str = Depends(actor_dependency)):
        return _response(request, toolchain_status(config_service.effective(), sum(1 for item in providers.list(actor) if item["enabled"])), "工具链状态获取成功")

    def active_tool(tool: str):
        if tool in RETIRED_TOOLS:
            raise HTTPException(410, "该工具已从工作台移除；历史配置保留，不再提供配置或探测入口")

    @core.get("/toolchain/{tool}/config", dependencies=[Depends(active_tool)])
    def tool_config(request: Request, tool: str, actor: str = Depends(actor_dependency), admin: bool = Depends(is_admin)):
        return _response(request, config_service.describe(tool, editable=admin))

    @core.post("/toolchain/{tool}/probe", dependencies=[Depends(active_tool)])
    async def test_integration(request: Request, tool: str, actor: str = Depends(actor_dependency), admin: bool = Depends(is_admin)):
        if not admin:
            raise HTTPException(403, "Administrator required")
        config_service.describe(tool, editable=False)
        from factory.tool_probe import probe
        return _response(request, await probe(tool, config_service.effective()))

    @core.put("/toolchain/{tool}/config", dependencies=[Depends(active_tool)])
    def save_tool_config(request: Request, tool: str, value: ToolSettingsInput, actor: str = Depends(actor_dependency), admin: bool = Depends(is_admin)):
        if not admin:
            raise HTTPException(403, "只有系统管理员可以修改全局工具配置")
        return _response(request, config_service.save(tool, value), "已保存；后续 API/活动读取新配置，外部服务部署仍需独立完成")

    @core.delete("/toolchain/{tool}/config", dependencies=[Depends(active_tool)])
    def reset_tool_config(request: Request, tool: str, revision: int, actor: str = Depends(actor_dependency), admin: bool = Depends(is_admin)):
        if not admin:
            raise HTTPException(403, "Administrator required")
        return _response(request, config_service.reset(tool, revision), "已恢复环境默认值；已保存覆盖值和凭据已清除")

    @core.post("/providers/export")
    def export_providers(request: Request, actor: str = Depends(actor_dependency)):
        return _response(request, export_config(providers.list(actor)))

    @core.post("/providers/{provider_id}/oauth/{action}")
    async def subscription_auth(request: Request, provider_id: str, action: Literal["begin", "restart", "poll", "disconnect"], actor: str = Depends(actor_dependency)):
        result = await run_in_threadpool(oauth.operation, actor, provider_id, action)
        return _response(request, result)

    @core.get("/providers/{provider_id}/oauth")
    async def subscription_status(request: Request, provider_id: str, actor: str = Depends(actor_dependency)):
        return _response(request, await run_in_threadpool(oauth.operation, actor, provider_id, "status"))

    @core.post("/providers/{provider_id}/discover")
    async def discover_saved_provider(request: Request, provider_id: str, actor: str = Depends(actor_dependency)):
        profile = await run_in_threadpool(providers.runtime, actor, provider_id)
        models = await discover_models(config_service.effective(), profile.provider, profile.base_url, profile.api_key)
        return _response(request, {"models": models})

    @core.get("/providers/catalog")
    def provider_catalog(request: Request, actor: str = Depends(actor_dependency)):
        return _response(request, catalog_payload(), "模型供应商目录获取成功")

    @core.get("/providers")
    def list_providers(request: Request, actor: str = Depends(actor_dependency)):
        return _response(request, providers.list(actor), "模型供应商列表获取成功")

    @core.post("/providers", status_code=201)
    def create_provider(request: Request, value: ProviderInput, actor: str = Depends(actor_dependency)):
        return _response(request, providers.create(actor, value), "模型供应商已创建")

    @core.put("/providers/{provider_id}")
    def update_provider(request: Request, provider_id: str, value: ProviderUpdate, actor: str = Depends(actor_dependency)):
        return _response(request, providers.update(actor, provider_id, value), "模型供应商已更新")

    @core.delete("/providers/{provider_id}")
    def delete_provider(request: Request, provider_id: str, actor: str = Depends(actor_dependency)):
        providers.delete(actor, provider_id)
        return _response(request, None, "模型供应商已删除")

    @core.post("/providers/{provider_id}/default")
    def default_provider(request: Request, provider_id: str, actor: str = Depends(actor_dependency)):
        return _response(request, providers.set_default(actor, provider_id), "已设为默认模型")

    @core.post("/providers/{provider_id}/test")
    async def test_provider(request: Request, provider_id: str, actor: str = Depends(actor_dependency)):
        result = await service.test_provider(actor, provider_id)
        return _response(request, result, "模型连通性测试成功")

    @core.post("/providers/discover")
    async def discover_provider_models(request: Request, value: DiscoverInput, actor: str = Depends(actor_dependency)):
        models = await discover_models(config_service.effective(), value.provider, value.base_url, value.api_key)
        return _response(request, {"models": models}, f"已发现 {len(models)} 个模型")

    @core.post("/projects", status_code=201)
    def create_project(request: Request, value: ProjectInput, actor: str = Depends(actor_dependency)):
        return _response(request, repo.create_project(actor, value), "项目已创建，下一步进行 AI 需求澄清")

    @core.get("/projects")
    def projects(request: Request, actor: str = Depends(actor_dependency)):
        return _response(request, repo.list_projects(actor), "项目列表获取成功")

    @core.get("/projects/{project_id}")
    def project(request: Request, project_id: str, actor: str = Depends(actor_dependency)):
        return _response(request, repo.get_project(actor, project_id), "项目详情获取成功")

    @core.post("/projects/{project_id}/messages")
    def message(request: Request, project_id: str, value: MessageInput, actor: str = Depends(actor_dependency)):
        return _response(request, repo.add_message(actor, project_id, value.content), "补充说明已保存，需要重新 AI 澄清")

    @core.post("/projects/{project_id}/clarify")
    async def clarify_project(request: Request, project_id: str, value: ClarifyInput, actor: str = Depends(actor_dependency)):
        saved = await service.clarify_project(actor, project_id, value.provider_id)
        return _response(request, saved, "需求已分析，可继续回答问题或进入规划")

    @core.post("/projects/{project_id}/runs", status_code=202)
    def run(request: Request, project_id: str, value: RunInput, actor: str = Depends(actor_dependency)):
        if value.sandbox == "cube" or value.provision_coder or value.pipeline_mode == "full":
            raise HTTPException(422, "CubeSandbox / Coder 已移除；新任务请使用 core 模式、static 或 docker 检查，并关闭 provision_coder")
        standard = not _legacy(request)
        if standard and not value.expected_revision:
            raise HTTPException(428, "请提交当前项目 expected_revision；刷新需求分析后再启动")
        if value.provider == "demo" and not value.provider_id and not settings.allow_legacy_demo:
            raise HTTPException(422, "固定 Demo 仅用于显式启用的本地测试；请先选择模型完成需求澄清")
        if standard and value.provider == "demo" and not value.provider_id:
            raise HTTPException(422, "新版工作台不允许固定 Demo 冒充 AI 分析；请配置真实模型供应商")
        if value.provider_id:
            profile = providers.runtime(actor, value.provider_id)
            value = value.model_copy(update={"provider": "litellm", "provider_id": profile.id})
        elif value.provider != "demo":
            profile = providers.runtime(actor, None)
            value = value.model_copy(update={"provider": "litellm", "provider_id": profile.id})
        active_settings = config_service.effective()
        selected = repo.get_project(actor, project_id)['template_id']
        java = selected == 'yudao-cloud-mini-antd-v1'
        if java and value.validation_level != 'runtime':
            raise HTTPException(422, '芋道模板需要选择 Docker 实际运行验收')
        if value.use_serena and not java and not active_settings.serena_url:
            raise HTTPException(422, "Configure the scoped ToolHive/Serena MCP endpoint first")
        if value.validation_level == 'runtime' and not java and not active_settings.runtime_verifier_image:
            raise HTTPException(422, "请先准备运行验收镜像，或明确选择仅源码检查")
        if value.sandbox == "docker" and value.validation_level != 'runtime' and not active_settings.docker_host_data_dir:
            raise HTTPException(422, "Configure Docker host-side data path and the sandbox override compose file")
        if java and not all((active_settings.yudao_upstream_dir / part / 'LICENSE').is_file() for part in ('backend', 'frontend')):
            raise HTTPException(503, '芋道模板源码未准备，请维护者执行 scripts/bootstrap_yudao.py 并挂载已锁定源码')
        if not java and not settings.upstream_dir.joinpath("LICENSE").exists():
            raise HTTPException(503, "Upstream template is missing; run scripts/bootstrap.py")
        return _response(request, repo.create_run(actor, project_id, value), "研发流水线已提交 Temporal")

    @core.get("/projects/{project_id}/runs")
    def runs(request: Request, project_id: str, actor: str = Depends(actor_dependency)):
        return _response(request, repo.list_runs(actor, project_id), "任务列表获取成功")

    @core.get("/runs/{run_id}")
    def get_run(request: Request, run_id: str, actor: str = Depends(actor_dependency)):
        return _response(request, repo.get_run(actor, run_id), "任务详情获取成功")

    @core.post("/runs/{run_id}/decision")
    def decision(request: Request, run_id: str, value: ApprovalInput, actor: str = Depends(actor_dependency)):
        return _response(request, repo.decide(actor, run_id, value), "人工决策已记录")

    @core.get("/runs/{run_id}/events")
    def events(request: Request, run_id: str, after: int = Query(0, ge=0), actor: str = Depends(actor_dependency)):
        return _response(request, repo.events(actor, run_id, after), "运行事件获取成功")

    @core.get("/runs/{run_id}/analysis")
    def analysis_artifacts(request: Request, run_id: str, actor: str = Depends(actor_dependency)):
        return _response(request, service.analysis_files(actor, run_id), "分析产物列表获取成功")

    @core.get("/runs/{run_id}/analysis/file", summary="读取当前用户的规格/架构产物")
    def analysis_file(run_id: str, path: str = Query(min_length=1, max_length=300), actor: str = Depends(actor_dependency)):
        file = service.analysis_file(actor, run_id, path)
        return FileResponse(file, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                          "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"})

    @core.get("/runs/{run_id}/download")
    def download(run_id: str, actor: str = Depends(actor_dependency)):
        with db.session() as session:
            r = session.scalar(select(Run).where(Run.id == run_id, Run.owner_id == actor))
            if not r:
                raise HTTPException(404, "Run not found")
            if r.status != "READY" or not r.artifact:
                raise HTTPException(409, "Artifact is not ready")
            artifact = (settings.data_dir / r.artifact).resolve()
            if not artifact.is_relative_to(settings.data_dir.resolve()) or not artifact.is_file():
                raise HTTPException(404, "Artifact file unavailable")
            if file_sha256(artifact) != r.artifact_sha256:
                raise HTTPException(409, "Artifact integrity check failed")
            return FileResponse(artifact, media_type="application/zip", filename=f"{r.spec['slug']}.zip", headers={"Cache-Control": "no-store", "X-Content-SHA256": r.artifact_sha256})

    @core.post("/runs/{run_id}/coder")
    async def coder(request: Request, run_id: str, actor: str = Depends(actor_dependency)):
        active_settings = config_service.effective()
        if not active_settings.coder_owner_id or actor != active_settings.coder_owner_id:
            raise HTTPException(403, "Coder provisioning is restricted to the explicitly configured administrator")
        run_value = repo.get_run(actor, run_id)
        if run_value["status"] != "READY":
            raise HTTPException(409, "Finish generating the source archive first")
        from factory.providers.coder import CoderClient
        try:
            result = await CoderClient(active_settings).create_workspace(run_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc
        return _response(request, result, "Coder 工作区已创建")

    @core.get("/transfer/{run_id}", include_in_schema=False)
    def source_transfer(run_id: str, authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(403, "Source capability required")
        with db.session() as session:
            row = session.get(Run, run_id)
            if not row or not row.artifact or not row.decision or not row.decision.get("approve"):
                raise HTTPException(403, "Source capability unavailable")
            verify_source_ticket(authorization[7:], run_id, row.artifact_sha256, settings)
            artifact = (settings.data_dir / row.artifact).resolve()
            if not artifact.is_relative_to(settings.data_dir.resolve()) or not artifact.is_file():
                raise HTTPException(404, "Artifact unavailable")
            if file_sha256(artifact) != row.artifact_sha256:
                raise HTTPException(409, "Artifact integrity check failed")
            return FileResponse(artifact, media_type="application/zip", headers={"Cache-Control": "no-store", "X-Content-SHA256": row.artifact_sha256})

    def response_mode(legacy: bool):
        # Included-router internals differ across FastAPI versions. Bind the mode
        # explicitly instead of inferring it from scope["route"].path/root_path.
        def mark(request: Request):
            request.state.factory_legacy = legacy
        return Depends(mark)

    router.include_router(core, prefix="/factory", dependencies=[response_mode(False)])
    router.include_router(core, prefix="/factory-api", dependencies=[response_mode(True)], include_in_schema=False)
    return router

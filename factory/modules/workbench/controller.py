from __future__ import annotations

import json
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header
from fastapi.routing import APIRoute
from fastapi.responses import FileResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text

from factory.config import ROOT, Settings
from factory.database import Database, Run
from factory.providers.registry import ProviderService
from .crud import Repository
from .schema import ApprovalInput, ClarifyInput, MessageInput, ProjectInput, ProviderInput, ProviderUpdate, RunInput
from .service import WorkbenchService
from factory.security import file_sha256
from factory.handoff import verify_source_ticket
from factory.toolchain import require_full_toolchain, toolchain_status


def _legacy(request: Request) -> bool:
    return request.scope["route"].path.startswith("/factory-api/")


def create_router(db: Database, settings: Settings, actor_dependency: Callable, *,
                  route_class: type[APIRoute] = APIRoute, response_factory: Callable | None = None) -> APIRouter:
    router = APIRouter(tags=["AI研发平台"])
    core = APIRouter(route_class=route_class)
    repo = Repository(db)
    providers = ProviderService(db, settings)
    service = WorkbenchService(db, settings)

    def _success(data=None, msg: str = "操作成功", status_code: int = 200):
        if response_factory is not None:
            return response_factory(data=data, msg=msg, status_code=status_code)
        return JSONResponse(jsonable_encoder({"code": 0, "msg": msg, "data": data, "success": True}), status_code=status_code)

    def _response(request: Request, data=None, msg: str = "操作成功"):
        if _legacy(request):
            return data
        return _success(data, msg, request.scope["route"].status_code or 200)

    @core.get("/health")
    def health(request: Request):
        with db.session() as session:
            session.execute(text("SELECT 1"))
        return _response(request, {"status": "ok", "version": "0.2.0", "scope": "API + database"}, "平台服务正常")

    @core.get("/templates")
    def templates(request: Request, actor: str = Depends(actor_dependency)):
        data = [json.loads((ROOT / "templates/fastapiadmin/manifest.json").read_text(encoding="utf-8"))]
        return _response(request, data, "模板列表获取成功")

    @core.get("/integrations")
    def integrations(request: Request, actor: str = Depends(actor_dependency)):
        rows = toolchain_status(settings, sum(1 for item in providers.list(actor) if item["enabled"]))
        if _legacy(request):
            return {row["id"]: ("configured" if row["configured"] else "not_configured") for row in rows}
        return _success(rows, "工具链状态获取成功")

    @core.get("/toolchain")
    def toolchain(request: Request, actor: str = Depends(actor_dependency)):
        return _response(request, toolchain_status(settings, sum(1 for item in providers.list(actor) if item["enabled"])), "工具链状态获取成功")

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
        standard = not _legacy(request)
        if standard and value.provider == "demo" and not value.provider_id:
            raise HTTPException(422, "新版工作台不允许固定 Demo 冒充 AI 分析；请配置真实模型供应商")
        if value.provider_id:
            profile = providers.runtime(actor, value.provider_id)
            value = value.model_copy(update={"provider": "litellm", "provider_id": profile.id})
        elif value.provider != "demo":
            profile = providers.runtime(actor, None)
            value = value.model_copy(update={"provider": "litellm", "provider_id": profile.id})
        if value.use_serena and not settings.serena_url:
            raise HTTPException(422, "Configure the scoped ToolHive/Serena MCP endpoint first")
        if value.sandbox == "cube" and not all([settings.cube_api_url, settings.cube_api_key, settings.cube_template]):
            raise HTTPException(422, "Cube API URL, key, and verified template are all required")
        if value.sandbox == "docker" and not settings.docker_host_data_dir:
            raise HTTPException(422, "Configure Docker host-side data path and the sandbox override compose file")
        if not settings.upstream_dir.joinpath("LICENSE").exists():
            raise HTTPException(503, "Upstream template is missing; run scripts/bootstrap.py")
        if value.pipeline_mode == "full":
            if value.provider == "demo":
                raise HTTPException(422, "完整工具链不支持固定 Demo；必须先完成真实 AI 需求澄清")
            if value.sandbox != "cube" or not value.use_serena or not value.provision_coder:
                raise HTTPException(422, "完整模式固定启用 ToolHive/Serena、CubeSandbox 和 Coder；部分执行请切换到基础模式")
            try:
                require_full_toolchain(settings, owner=actor, provider_count=sum(1 for item in providers.list(actor) if item["enabled"]), sandbox=value.sandbox, provision_coder=value.provision_coder)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
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
        if not settings.coder_owner_id or actor != settings.coder_owner_id:
            raise HTTPException(403, "Coder provisioning is restricted to the explicitly configured administrator")
        run_value = repo.get_run(actor, run_id)
        if run_value["status"] != "READY":
            raise HTTPException(409, "Finish generating the source archive first")
        from factory.providers.coder import CoderClient
        try:
            result = await CoderClient(settings).create_workspace(run_id)
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

    router.include_router(core, prefix="/factory")
    router.include_router(core, prefix="/factory-api", include_in_schema=False)
    return router

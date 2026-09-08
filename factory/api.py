from __future__ import annotations

import json
from pathlib import Path
from typing import Callable
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from .config import ROOT, Settings
from .database import Database, Run
from .repository import Repository
from .schemas import ProjectInput, MessageInput, RunInput, ApprovalInput
from .security import file_sha256


def create_router(db: Database, settings: Settings, actor_dependency: Callable) -> APIRouter:
    router = APIRouter(prefix="/factory-api", tags=["AI R&D Factory"])
    repo = Repository(db)

    @router.get("/health")
    def health():
        with db.session() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "version": "0.1.0", "scope": "API + database only; not worker readiness"}

    @router.get("/templates")
    def templates(actor: str = Depends(actor_dependency)):
        return [json.loads((ROOT / "templates/fastapiadmin/manifest.json").read_text(encoding="utf-8"))]

    @router.get("/integrations")
    def integrations(actor: str = Depends(actor_dependency)):
        # 'configured' is not a health claim. External smoke checks are separate commands.
        return {"langgraph": "runtime_dependency", "temporal": "runtime_dependency",
                "openspec": "cli_quality_gate", "diagrams": "runtime_renderer", "structurizr": "dsl_export_and_optional_viewer",
                "litellm": "configured" if settings.model_api_key else "not_configured",
                "toolhive_serena": "configured_unverified" if settings.serena_url else "not_configured",
                "cube": "configured_unverified" if settings.cube_api_url else "not_configured",
                "coder": "configured_unverified" if settings.coder_template_id else "not_configured"}

    @router.post("/projects", status_code=201)
    def create_project(value: ProjectInput, actor: str = Depends(actor_dependency)):
        return repo.create_project(actor, value)

    @router.get("/projects")
    def projects(actor: str = Depends(actor_dependency)):
        return repo.list_projects(actor)

    @router.get("/projects/{project_id}")
    def project(project_id: str, actor: str = Depends(actor_dependency)):
        return repo.get_project(actor, project_id)

    @router.post("/projects/{project_id}/messages")
    def message(project_id: str, value: MessageInput, actor: str = Depends(actor_dependency)):
        return repo.add_message(actor, project_id, value.content)

    @router.post("/projects/{project_id}/runs", status_code=202)
    def run(project_id: str, value: RunInput, actor: str = Depends(actor_dependency)):
        if value.provider == "litellm" and not settings.model_api_key:
            raise HTTPException(422, "Configure the LiteLLM gateway key first; no implicit demo fallback")
        if value.use_serena and not settings.serena_url:
            raise HTTPException(422, "Configure the scoped ToolHive/Serena MCP endpoint first")
        if value.sandbox == "cube" and not all([settings.cube_api_url, settings.cube_api_key, settings.cube_template]):
            raise HTTPException(422, "Cube API URL, key, and verified template are all required")
        if value.sandbox == "docker" and not settings.docker_host_data_dir:
            raise HTTPException(422, "Configure Docker host-side data path and the sandbox override compose file")
        if not settings.upstream_dir.joinpath("LICENSE").exists():
            raise HTTPException(503, "Upstream template is missing; run scripts/bootstrap.py")
        return repo.create_run(actor, project_id, value)

    @router.get("/projects/{project_id}/runs")
    def runs(project_id: str, actor: str = Depends(actor_dependency)):
        return repo.list_runs(actor, project_id)

    @router.get("/runs/{run_id}")
    def get_run(run_id: str, actor: str = Depends(actor_dependency)):
        return repo.get_run(actor, run_id)

    @router.post("/runs/{run_id}/decision")
    def decision(run_id: str, value: ApprovalInput, actor: str = Depends(actor_dependency)):
        return repo.decide(actor, run_id, value)

    @router.get("/runs/{run_id}/events")
    def events(run_id: str, after: int = Query(0, ge=0), actor: str = Depends(actor_dependency)):
        return repo.events(actor, run_id, after)

    @router.get("/runs/{run_id}/download")
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
            return FileResponse(artifact, media_type="application/zip", filename=f"{r.spec['slug']}.zip",
                                headers={"Cache-Control": "no-store", "X-Content-SHA256": r.artifact_sha256})

    @router.post("/runs/{run_id}/coder")
    async def coder(run_id: str, actor: str = Depends(actor_dependency)):
        if not settings.coder_owner_id or actor != settings.coder_owner_id:
            raise HTTPException(403, "Coder provisioning is restricted to the explicitly configured administrator")
        run_value = repo.get_run(actor, run_id)
        if run_value["status"] != "READY":
            raise HTTPException(409, "Finish generating the source archive first")
        from .providers.coder import CoderClient
        try:
            # Creates a workspace using an administrator-registered Coder template.
            # No implicit source upload and no platform token in the workspace.
            return await CoderClient(settings).create_workspace(run_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc

    return router

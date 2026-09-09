"""Workbench application service; controllers do not own analysis or file IO policy."""
from pathlib import Path

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from factory.clarifier import clarify
from factory.config import Settings
from factory.database import Database
from factory.providers.llm import ModelGateway
from factory.providers.registry import ProviderService
from factory.security import safe_relative
from .crud import Repository

ANALYSIS_FILES = frozenset({
    "openspec/changes/create-product/proposal.md",
    "openspec/changes/create-product/design.md",
    "openspec/changes/create-product/requirements.md",
    "openspec/changes/create-product/tasks.md",
    "openspec/changes/create-product/specs/generated-business/spec.md",
    "architecture/workspace.dsl", "architecture/er.dot", "architecture/er.mmd",
    "architecture/er.svg", "architecture/deployment.py", "architecture/deployment.svg",
    "docs/DATA_DICTIONARY.md", "docs/tasks.dag.json",
})


class WorkbenchService:
    def __init__(self, db: Database, settings: Settings):
        self.settings = settings
        self.repo = Repository(db)
        self.providers = ProviderService(db, settings)

    async def clarify_project(self, owner: str, project_id: str, provider_id: str | None) -> dict:
        project = await run_in_threadpool(self.repo.get_project, owner, project_id)
        profile = await run_in_threadpool(self.providers.runtime, owner, provider_id)
        try:
            result = await clarify(project["messages"], project.get("clarification"), profile, self.settings)
        except Exception:
            # SDK error chains can include keys or URLs. Never expose raw exception text.
            raise HTTPException(502, "AI 需求澄清未完成，请检查模型连通性和结构化输出支持；未生成任何代码") from None
        return await run_in_threadpool(
            self.repo.save_clarification, owner, project_id, result, profile.id,
            expected_revision=project["revision"],
        )

    async def test_provider(self, owner: str, provider_id: str) -> dict:
        profile = await run_in_threadpool(self.providers.runtime, owner, provider_id)
        try:
            return await ModelGateway(self.settings).ping(profile)
        except Exception:
            raise HTTPException(502, "模型测试失败：请检查模型 ID、API Key、Base URL、配额及 Azure API Version") from None

    def _analysis_root(self, owner: str, run_id: str) -> Path:
        self.repo.get_run(owner, run_id)
        return self.settings.data_dir.resolve() / "runs" / run_id / "analysis"

    def analysis_files(self, owner: str, run_id: str) -> list[str]:
        base = self._analysis_root(owner, run_id)
        return sorted(name for name in ANALYSIS_FILES if (base / name).is_file()
                      and (base / name).resolve().is_relative_to(base))

    def analysis_file(self, owner: str, run_id: str, name: str) -> Path:
        base = self._analysis_root(owner, run_id)
        try:
            relative = safe_relative(name)
        except ValueError:
            raise HTTPException(404, "Analysis artifact not found") from None
        path = (base / relative).resolve()
        if name not in ANALYSIS_FILES or not path.is_relative_to(base) or not path.is_file():
            raise HTTPException(404, "Analysis artifact not found")
        if path.stat().st_size > 4 * 1024 * 1024:
            raise HTTPException(413, "Artifact exceeds the 4 MiB preview limit")
        return path

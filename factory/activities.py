from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from temporalio import activity

from .artifacts import build_architecture, build_openspec
from .config import Settings
from .database import Database, Event, Run
from .generator import generate_product
from .evidence import source_digest, require_full_quality, require_full_delivery
from .security import file_sha256
from .handoff import issue_source_ticket
from .packaging import package_product
from .planner import plan
from .providers.coder import CoderClient
from .providers.mcp import SerenaClient
from .providers.registry import ProviderService
from .schemas import ProjectSpec
from .security import redact, run_path
from .toolchain import validate_structurizr
from .validation import verify_product


class Activities:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self._settings = settings
        self.db = db
        self.providers = ProviderService(db, settings)

    @property
    def settings(self):
        from factory.tool_settings import ToolSettingsService
        return ToolSettingsService(self.db, self._settings).effective()

    def get(self, run_id: str) -> dict:
        with self.db.session() as session:
            row = session.get(Run, run_id)
            if not row:
                raise ValueError("Unknown run")
            return {
                "request": row.request, "owner": row.owner_id, "spec": row.spec, "digest": row.spec_digest,
                "artifact_sha256": row.artifact_sha256, "checks": row.checks, "stage_details": row.stage_details or {}, "status": row.status,
            }

    def stage(self, run_id: str, stage: str, status: str, message: str, *, tool: str,
              detail: dict | None = None, level: str = "info") -> None:
        with self.db.session() as session:
            row = session.get(Run, run_id)
            if not row:
                raise ValueError("Unknown run")
            row.status = status
            details = dict(row.stage_details or {})
            details[stage] = {**(detail or {}), "status": status, "tool": tool}
            row.stage_details = details
            session.add(Event(run_id=run_id, level=level, stage=stage, tool=tool, payload=detail, message=message))

    @activity.defn(name="rnd.context")
    async def context_activity(self, run_id: str) -> dict:
        info = self.get(run_id)
        req = info["request"]
        if not req.get("use_serena"):
            self.stage(run_id, "context", "CONTEXT_READY", "本次任务未请求 Serena 上下文。", tool="toolhive+serena", detail={"used": False})
            return {"context": ""}
        self.stage(run_id, "context", "CONTEXT_LOADING", "通过 ToolHive 管理的只读 Serena MCP 读取 Golden Template 符号上下文。", tool="toolhive+serena")
        context = await SerenaClient(self.settings).template_context()
        self.stage(run_id, "context", "CONTEXT_READY", "Serena 模板上下文已读取并限制在 16 KiB 内。", tool="toolhive+serena", detail={"used": True, "chars": len(context)})
        return {"context": context[:16000]}

    @activity.defn(name="rnd.plan")
    async def plan_activity(self, value: dict | str) -> dict:
        legacy = isinstance(value, str)
        value = {"run_id": value} if legacy else value
        run_id = value["run_id"]
        info = self.get(run_id)
        if info["spec"]:
            return {"digest": info["digest"]}
        self.stage(run_id, "plan", "PLANNING", "LangGraph 根据已澄清需求生成受约束 ProjectSpec；失败会携带校验错误重试一次。", tool="langgraph+litellm")
        req = info["request"]
        requirement = "\n\n".join(m.get("content", "") for m in req["messages"] if m.get("role") == "user")
        clarification = req.get("clarification") or {}
        requirement += "\n\n已确认的需求分析：\n" + str(clarification)
        if req.get("provider") == "demo" and not req.get("provider_id"):
            provider = "demo"
        else:
            provider = self.providers.runtime(info["owner"], req.get("provider_id") or req.get("clarification_provider_id"))
        spec = await plan(requirement, provider, False, self.settings, context=value.get("context", ""))
        with self.db.session() as session:
            row = session.get(Run, run_id)
            row.spec = spec.model_dump(); row.spec_digest = spec.digest()
            details = dict(row.stage_details or {})
            details["plan"] = {"status": "PLANNED", "tool": "langgraph+litellm", "digest": spec.digest()}
            row.stage_details = details; row.status = "AWAITING_APPROVAL" if legacy else "PLANNED"
            session.add(Event(run_id=run_id, stage="plan", tool="langgraph+litellm", message="结构化规格已保存，开始生成可审阅的规格与架构包。"))
        return {"digest": spec.digest()}

    def _validate_openspec(self, root: Path) -> dict:
        binary = shutil.which("openspec")
        if not binary:
            raise RuntimeError("OpenSpec CLI missing. Install @fission-ai/openspec@1.12.0")
        result = subprocess.run(
            [binary, "validate", "create-product", "--type", "change", "--strict", "--no-interactive"],
            cwd=root, text=True, capture_output=True, timeout=45,
            env={"PATH": os.environ.get("PATH", ""), "HOME": "/tmp", "LANG": "C.UTF-8", "OPENSPEC_TELEMETRY": "0", "CI": "1"},
        )
        output = (result.stdout + result.stderr)[-4000:]
        if result.returncode:
            raise RuntimeError("OpenSpec analysis validation failed: " + output[-1800:])
        return {"validated": True, "output": output}

    @activity.defn(name="rnd.analysis_pack")
    async def analysis_pack_activity(self, run_id: str) -> dict:
        info = self.get(run_id); spec = ProjectSpec.model_validate(info["spec"])
        root = run_path(self.settings.data_dir, run_id) / "analysis"
        self.stage(run_id, "openspec", "SPEC_PACK_BUILDING", "生成 OpenSpec proposal/design/tasks/spec 并执行 strict validate。", tool="openspec")
        root.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(build_openspec, root, spec, generated=False, clarification=info["request"].get("clarification"))
        openspec = await asyncio.to_thread(self._validate_openspec, root)
        self.stage(run_id, "openspec", "SPEC_PACK_READY", "OpenSpec 规格包已通过严格校验。", tool="openspec", detail=openspec)
        self.stage(run_id, "architecture", "ARCHITECTURE_BUILDING", "从同一 ProjectSpec 生成 Structurizr C4 DSL、ER 图和 mingrammer/diagrams 部署图。", tool="structurizr+diagrams")
        architecture = await asyncio.to_thread(build_architecture, root, spec, diagrams_required=self.settings.diagrams_required)
        req = info["request"]
        if req.get("pipeline_mode") == "full":
            structurizr = await asyncio.to_thread(validate_structurizr, root, run_id, self.settings)
            architecture["structurizr"] = structurizr; architecture["c4_dsl"] = "parser_validated"
        else:
            architecture["structurizr"] = {"validated": False, "reason": "core mode"}
        self.stage(run_id, "architecture", "ARCHITECTURE_READY", "架构预览包已生成；完整模式同时执行 Structurizr parser 验证。", tool="structurizr+diagrams", detail=architecture)
        with self.db.session() as session:
            row = session.get(Run, run_id); row.status = "AWAITING_APPROVAL"
            session.add(Event(run_id=run_id, stage="human_gate", tool="temporal", message="需求规格、OpenSpec 和架构包已准备完成。等待你确认数据结构、未支持项和验收标准。"))
        return {"digest": info["digest"], "openspec": openspec, "architecture": architecture}

    @activity.defn(name="rnd.generate")
    async def generate_activity(self, run_id: str) -> dict:
        info = self.get(run_id)
        self.stage(run_id, "generate", "GENERATING", "从固定 FastapiAdmin 模板生成后端扩展、迁移、Vue 页面和交付架构包。", tool="fastapiadmin+factory")
        product = run_path(self.settings.data_dir, run_id) / "product"
        result = await asyncio.to_thread(generate_product, ProjectSpec.model_validate(info["spec"]), self.settings.upstream_dir, product, diagrams_required=self.settings.diagrams_required)
        # Keep the approved requirements and parser receipt in the delivered source, not only the preview.
        await asyncio.to_thread(build_openspec, product, ProjectSpec.model_validate(info["spec"]),
                                clarification=info["request"].get("clarification"))
        analysis_dsl = run_path(self.settings.data_dir, run_id) / "analysis/architecture/workspace.dsl"
        architecture = info["stage_details"].get("architecture", {})
        if architecture.get("c4_dsl") == "parser_validated":
            if analysis_dsl.read_bytes() != (product / "architecture/workspace.dsl").read_bytes():
                raise RuntimeError("Delivered C4 DSL differs from the approved, validated source")
            import json
            receipt_path = product / "delivery/receipt.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["architecture"]["c4_dsl"] = "parser_validated"
            receipt["architecture"]["structurizr"] = architecture["structurizr"]
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
        self.stage(run_id, "generate", "GENERATED", "FastapiAdmin 产品源码已物化。", tool="fastapiadmin+factory", detail={"status": result.get("status")})
        return result

    @activity.defn(name="rnd.verify")
    async def verify_activity(self, run_id: str) -> dict:
        info = self.get(run_id); sandbox = info["request"].get("sandbox", "static")
        self.stage(run_id, "sandbox", "VERIFYING", f"执行源代码、业务契约、OpenSpec 与 {sandbox} 沙箱检查。", tool="cube" if sandbox == "cube" else sandbox)
        report = await asyncio.to_thread(verify_product, run_path(self.settings.data_dir, run_id) / "product", run_id, info["request"], self.settings)
        with self.db.session() as session:
            session.get(Run, run_id).checks = report
        self.stage(run_id, "sandbox", "VERIFIED", "沙箱与质量门禁完成；仍需区分 scaffold checks 与完整生产验收。", tool="cube" if sandbox == "cube" else sandbox, detail={"quality_level": report.get("quality_level"), "provider": sandbox})
        return {"verified": report.get("quality_level", "scaffold_ready")}

    @activity.defn(name="rnd.package")
    async def package_activity(self, run_id: str) -> dict:
        info = self.get(run_id)
        if not info["checks"]:
            raise ValueError("Cannot package an unverified product")
        self.stage(run_id, "package", "PACKAGING", "排除密钥与缓存，生成 manifest 并计算交付 ZIP 哈希。", tool="factory-packager")
        base = run_path(self.settings.data_dir, run_id)
        if info["checks"].get("source_digest") != await asyncio.to_thread(source_digest, base / "product"):
            raise RuntimeError("Verified source changed before packaging; verification must be rerun")
        if info["request"].get("pipeline_mode") == "full":
            require_full_quality(info["checks"])
        sha = await asyncio.to_thread(package_product, base / "product", base / "product.zip", info["checks"])
        with self.db.session() as session:
            row = session.get(Run, run_id); row.artifact = str((base / "product.zip").relative_to(self.settings.data_dir.resolve())); row.artifact_sha256 = sha; row.status = "PACKAGED"
        self.stage(run_id, "package", "PACKAGED", "交付 ZIP 已生成并记录 SHA-256。", tool="factory-packager", detail={"sha256": sha})
        # Pre-upgrade histories have no rnd.ready activity; preserve their terminal semantics.
        if "pipeline_mode" not in info["request"]:
            with self.db.session() as session:
                session.get(Run, run_id).status = "READY"
        return {"sha256": sha}

    @activity.defn(name="rnd.coder")
    async def coder_activity(self, run_id: str) -> dict:
        info = self.get(run_id); req = info["request"]
        if not req.get("provision_coder"):
            self.stage(run_id, "coder", "CODER_SKIPPED", "本次任务未请求 Coder 工作区。", tool="coder", detail={"used": False}); return {"used": False}
        if not self.settings.coder_owner_id or info["owner"] != self.settings.coder_owner_id:
            raise RuntimeError("Coder auto provisioning is restricted to FACTORY_CODER_OWNER_ID")
        self.stage(run_id, "coder", "CODER_PROVISIONING", "通过 Coder API 创建长期 IDE 工作区。", tool="coder")
        source = None
        if self.settings.coder_auto_import:
            source = {"url": self.settings.coder_factory_url.rstrip("/") + "/factory/transfer/" + run_id,
                      "sha256": info["artifact_sha256"],
                      "token": issue_source_ticket(run_id, info["artifact_sha256"], self.settings)}
        result = await CoderClient(self.settings).create_workspace(run_id, source=source)
        if req.get("pipeline_mode") == "full" and result.get("source_import") != "sha256_verified":
            raise RuntimeError("Complete pipeline requires verified Coder source import")
        with self.db.session() as session:
            row = session.get(Run, run_id); checks = dict(row.checks or {}); checks["coder"] = result; row.checks = checks
        self.stage(run_id, "coder", "CODER_READY", "Coder 已返回工作区状态与源码导入回执。", tool="coder", detail=result)
        return result

    @activity.defn(name="rnd.ready")
    async def ready_activity(self, run_id: str) -> dict:
        with self.db.session() as session:
            row = session.get(Run, run_id)
            if not row.artifact or not row.checks or not (row.decision or {}).get("approve"):
                raise RuntimeError("Cannot mark run READY without approval, verification and an artifact")
            details = row.stage_details or {}
            artifact = (self.settings.data_dir / row.artifact).resolve()
            if not artifact.is_relative_to(self.settings.data_dir.resolve()) or not artifact.is_file():
                raise RuntimeError("Delivery archive is missing")
            if file_sha256(artifact) != row.artifact_sha256:
                raise RuntimeError("Delivery archive changed after packaging")
            if row.request.get("pipeline_mode") == "full":
                require_full_delivery(row.checks, details, row.artifact_sha256)
            row.status = "READY"
            row.stage_details = {**details, "complete": {"status": "READY", "tool": "temporal"}}
            session.add(Event(run_id=run_id, stage="complete", tool="temporal", message="本次所选流水线已结束，源码包可下载。源码交付与生产验收状态分别记录。"))
        return {"status": "READY"}

    @activity.defn(name="rnd.terminal")
    async def terminal(self, value: dict) -> None:
        run_id = value["run_id"]
        message = redact(value.get("error", ""), [self.settings.model_api_key, self.settings.cube_api_key, self.settings.coder_token, self.settings.serena_token, self.settings.credential_encryption_key])
        status = value["status"]
        with self.db.session() as session:
            row = session.get(Run, run_id)
            if row.status == "READY": return
            details = dict(row.stage_details or {})
            if status == "FAILED":
                for key, detail in details.items():
                    if detail.get("status") in {"CONTEXT_LOADING", "PLANNING", "SPEC_PACK_BUILDING",
                                               "ARCHITECTURE_BUILDING", "GENERATING", "VERIFYING",
                                               "PACKAGING", "CODER_PROVISIONING"}:
                        details[key] = {**detail, "status": "FAILED", "error": message}
            row.stage_details = details
            row.status = status; row.error = message or None
            session.add(Event(run_id=run_id, level="error" if status == "FAILED" else "info", stage="terminal", tool="temporal", message=f"任务结束：{status}。{message}"))

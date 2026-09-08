from __future__ import annotations

from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .database import Database, Project, Run, Event, Outbox
from .schemas import ProjectInput, RunInput, ApprovalInput

TERMINAL = {"READY", "FAILED", "REJECTED", "CANCELLED"}


def run_dict(run: Run) -> dict:
    return {name: getattr(run, name) for name in ["id", "project_id", "status", "spec", "spec_digest", "decision",
                                                "artifact_sha256", "checks", "error", "created_at", "updated_at"]} | {
        "provider": run.request["provider"], "sandbox": run.request["sandbox"],
        "download_available": run.status == "READY" and bool(run.artifact),
        "quality_label": "scaffold_ready" if run.status == "READY" else None}


class Repository:
    def __init__(self, db: Database):
        self.db = db

    def create_project(self, owner: str, value: ProjectInput) -> dict:
        if value.template_id != "fastapiadmin-pg-v1":
            raise HTTPException(422, "This version implements only fastapiadmin-pg-v1")
        with self.db.session() as session:
            p = Project(id=str(uuid4()), owner_id=owner, title=value.title, template_id=value.template_id,
                        messages=[{"role": "user", "content": value.requirement}])
            session.add(p)
            session.flush()
            return self.project_dict(p)

    @staticmethod
    def project_dict(p: Project) -> dict:
        return {k: getattr(p, k) for k in ["id", "title", "template_id", "messages", "created_at"]}

    def get_project(self, owner: str, project_id: str) -> dict:
        with self.db.session() as session:
            p = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner))
            if not p:
                raise HTTPException(404, "Project not found")
            return self.project_dict(p)

    def list_projects(self, owner: str) -> list[dict]:
        with self.db.session() as session:
            return [self.project_dict(p) for p in session.scalars(select(Project).where(Project.owner_id == owner)
                                                                 .order_by(Project.created_at.desc()).limit(100))]

    def add_message(self, owner: str, project_id: str, content: str) -> dict:
        with self.db.session() as session:
            p = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner).with_for_update())
            if not p:
                raise HTTPException(404, "Project not found")
            messages = [*p.messages, {"role": "user", "content": content}]
            if len(messages) > 20 or sum(len(m["content"]) for m in messages) > 40000:
                raise HTTPException(422, "Conversation limit reached; create a new project with a consolidated requirement")
            p.messages = messages
            return self.project_dict(p)

    def create_run(self, owner: str, project_id: str, value: RunInput) -> dict:
        def existing():
            with self.db.session() as session:
                r = session.scalar(select(Run).where(Run.owner_id == owner, Run.idempotency_key == value.idempotency_key))
                if r:
                    same = r.project_id == project_id and all(r.request.get(k) == v for k, v in value.model_dump().items())
                    if not same:
                        raise HTTPException(409, "Idempotency key was already used with a different request")
                    return run_dict(r)
            return None
        found = existing()
        if found:
            return found
        try:
            with self.db.session() as session:
                p = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner))
                if not p:
                    raise HTTPException(404, "Project not found")
                r = Run(id=str(uuid4()), project_id=p.id, owner_id=owner, idempotency_key=value.idempotency_key,
                        request=value.model_dump() | {"messages": p.messages, "template_id": p.template_id}, status="QUEUED")
                session.add(r)
                session.flush()
                session.add(Outbox(run_id=r.id, kind="start"))
                session.add(Event(run_id=r.id, message="任务已持久化。等待 Temporal dispatcher 接收。"))
                return run_dict(r)
        except IntegrityError:
            found = existing()
            if found:
                return found
            raise

    def get_run(self, owner: str, run_id: str) -> dict:
        with self.db.session() as session:
            r = session.scalar(select(Run).where(Run.id == run_id, Run.owner_id == owner))
            if not r:
                raise HTTPException(404, "Run not found")
            return run_dict(r)

    def list_runs(self, owner: str, project_id: str) -> list[dict]:
        self.get_project(owner, project_id)
        with self.db.session() as session:
            return [run_dict(r) for r in session.scalars(select(Run).where(Run.project_id == project_id, Run.owner_id == owner)
                                                        .order_by(Run.created_at.desc()).limit(100))]

    def decide(self, owner: str, run_id: str, value: ApprovalInput) -> dict:
        with self.db.session() as session:
            r = session.scalar(select(Run).where(Run.id == run_id, Run.owner_id == owner).with_for_update())
            if not r:
                raise HTTPException(404, "Run not found")
            decision = value.model_dump()
            if r.decision:
                if r.decision == decision:
                    return run_dict(r)
                raise HTTPException(409, "Decision already recorded; create a new run to change the approved schema")
            if r.status != "AWAITING_APPROVAL" or r.spec_digest != value.spec_digest:
                raise HTTPException(409, "Approval must match the current waiting schema digest")
            if value.approve and r.spec.get("unsupported_features") and not value.accept_limitations:
                raise HTTPException(422, "Review and explicitly accept unsupported features before approval")
            r.decision = decision
            session.add(Outbox(run_id=r.id, kind="decision"))
            session.add(Event(run_id=r.id, message="人工决定已记录，并进入可靠信号发件箱。"))
            return run_dict(r)

    def events(self, owner: str, run_id: str, after: int = 0) -> list[dict]:
        self.get_run(owner, run_id)
        with self.db.session() as session:
            return [{"id": e.id, "level": e.level, "message": e.message, "created_at": e.created_at}
                    for e in session.scalars(select(Event).where(Event.run_id == run_id, Event.id > after)
                                             .order_by(Event.id).limit(200))]

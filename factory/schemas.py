from __future__ import annotations

import hashlib
import json
import keyword
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
RESERVED = {"id", "owner_id", "created_at", "updated_at", "metadata", "schema", "type", "user"}
ProviderKind = Literal[
    "openai", "anthropic", "azure_openai", "google", "deepseek", "groq",
    "openrouter", "ollama", "mistral", "xai", "litellm_proxy", "custom_openai",
]
PipelineMode = Literal["core", "full"]


def identifier(value: str) -> str:
    if not IDENTIFIER.fullmatch(value) or keyword.iskeyword(value):
        raise ValueError("Use a lowercase snake_case identifier, at most 40 characters")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldSpec(StrictModel):
    name: str
    label: str = Field(min_length=1, max_length=80)
    kind: Literal["string", "text", "integer", "number", "boolean", "date", "datetime", "reference"]
    required: bool = True
    references: str | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        identifier(value)
        if value in RESERVED:
            raise ValueError(f"Reserved field name: {value}")
        return value

    @model_validator(mode="after")
    def check_reference(self) -> "FieldSpec":
        if self.kind == "reference":
            if not self.references:
                raise ValueError("A reference field must specify references")
            identifier(self.references)
        elif self.references is not None:
            raise ValueError("Only reference fields may specify references")
        return self


class EntitySpec(StrictModel):
    name: str
    label: str = Field(min_length=1, max_length=80)
    fields: list[FieldSpec] = Field(min_length=1, max_length=16)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        identifier(value)
        if value in {"schema", "docs", "openapi", "health"}:
            raise ValueError("Reserved entity route name")
        return value

    @model_validator(mode="after")
    def unique_fields(self) -> "EntitySpec":
        names = [f.name for f in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate field names")
        return self


class ProjectSpec(StrictModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{1,49}$")
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=2000)
    entities: list[EntitySpec] = Field(min_length=1, max_length=8)
    unsupported_features: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def references_and_cycles(self) -> "ProjectSpec":
        names = [e.name for e in self.entities]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate entity names")
        edges: dict[str, set[str]] = {n: set() for n in names}
        for entity in self.entities:
            for field in entity.fields:
                if field.kind == "reference":
                    if field.references not in edges:
                        raise ValueError(f"Unknown reference target: {field.references}")
                    edges[entity.name].add(field.references)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(n: str) -> None:
            if n in visiting:
                raise ValueError("v0.2 supports acyclic parent/child relationships only")
            if n in visited:
                return
            visiting.add(n)
            for target in edges[n]:
                visit(target)
            visiting.remove(n)
            visited.add(n)
        for name in names:
            visit(name)
        return self

    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.model_dump()).encode()).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ProjectInput(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    requirement: str = Field(min_length=5, max_length=16000)
    template_id: str = "fastapiadmin-pg-v1"


class MessageInput(StrictModel):
    content: str = Field(min_length=1, max_length=16000)


class ProviderInput(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    provider: ProviderKind
    base_url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=4096)
    model: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    is_default: bool = False
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int = Field(default=6000, ge=256, le=128000)


class ProviderUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    provider: ProviderKind | None = None
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=4096)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    is_default: bool | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=256, le=128000)


class ClarifyInput(StrictModel):
    provider_id: str | None = Field(default=None, max_length=36)


class ClarificationResult(StrictModel):
    ready: bool
    understanding: str = Field(min_length=1, max_length=4000)
    questions: list[str] = Field(default_factory=list, max_length=12)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=30)
    risks: list[str] = Field(default_factory=list, max_length=20)
    suggested_stack: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def ready_is_actionable(self) -> "ClarificationResult":
        if self.ready and self.questions:
            raise ValueError("A ready clarification cannot contain unanswered blocking questions")
        if self.ready and not self.acceptance_criteria:
            raise ValueError("A ready clarification needs explicit acceptance criteria")
        if not self.ready and not self.questions:
            raise ValueError("A non-ready clarification must ask at least one blocking question")
        return self


class RunInput(StrictModel):
    provider_id: str | None = Field(default=None, max_length=36)
    # Backward-compatible field for older API clients. New UI uses provider_id only.
    provider: Literal["demo", "litellm"] | None = "demo"
    # Legacy raw /factory-api clients keep the original conservative defaults.
    # The new FastapiAdmin workbench sends the full-mode choices explicitly.
    use_serena: bool = False
    sandbox: Literal["static", "docker", "cube"] = "static"
    pipeline_mode: PipelineMode = "core"
    provision_coder: bool = False
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class ApprovalInput(StrictModel):
    spec_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approve: bool = True
    accept_limitations: bool = False


def demo_spec() -> ProjectSpec:
    """Test fixture only. The interactive demo no longer substitutes this for AI clarification."""
    return ProjectSpec.model_validate({
        "slug": "device-maintenance", "title": "设备检修管理示例",
        "summary": "测试夹具：设备及检修记录。交互式演示必须先经过真实 AI 澄清。",
        "entities": [
            {"name": "device", "label": "设备", "fields": [
                {"name": "name", "label": "设备名称", "kind": "string"},
                {"name": "code", "label": "设备编号", "kind": "string"},
                {"name": "enabled", "label": "是否启用", "kind": "boolean"}]},
            {"name": "maintenance", "label": "检修记录", "fields": [
                {"name": "device_id", "label": "设备 ID", "kind": "reference", "references": "device"},
                {"name": "performed_on", "label": "检修日期", "kind": "date"},
                {"name": "notes", "label": "检修内容", "kind": "text"}]}
        ],
        "unsupported_features": ["测试夹兛不代表 AI 已分析自由文本需求。"]
    })

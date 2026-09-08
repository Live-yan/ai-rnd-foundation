from __future__ import annotations

import hashlib
import json
import keyword
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
RESERVED = {"id", "owner_id", "created_at", "updated_at", "metadata", "schema", "type", "user"}


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
    def check_reference(self) -> FieldSpec:
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
    def unique_fields(self) -> EntitySpec:
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
    def references_and_cycles(self) -> ProjectSpec:
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
                raise ValueError("v0.1 supports acyclic parent/child relationships only")
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


class RunInput(StrictModel):
    provider: Literal["demo", "litellm"] = "demo"
    use_serena: bool = False
    sandbox: Literal["static", "docker", "cube"] = "static"
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class ApprovalInput(StrictModel):
    spec_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approve: bool = True
    accept_limitations: bool = False


def demo_spec() -> ProjectSpec:
    """Explicit fixed fixture. It does NOT infer arbitrary natural-language requirements."""
    return ProjectSpec.model_validate({
        "slug": "device-maintenance", "title": "设备检修管理示例",
        "summary": "固定离线示例：设备及检修记录。真实需求请使用 LiteLLM 模式。",
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
        "unsupported_features": ["演示模式不解析自由文本，生成的是固定设备检修示例。", "不包含审批流、支付、实时设备采集或生产级业务验收。"]
    })

from __future__ import annotations

import hashlib
import json
import keyword
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
RESERVED = {"id", "owner_id", "tenant_id", "created_at", "updated_at", "metadata", "schema", "type", "user"}
# Keep in sync with factory.providers.catalog.PROVIDER_CATALOG ids.
ProviderKind = Literal[
    "chatgpt", "openai", "anthropic", "azure_openai", "google", "deepseek", "groq",
    "openrouter", "ollama", "mistral", "xai", "litellm_proxy", "custom_openai",
    "cerebras", "together_ai", "fireworks_ai", "perplexity", "sambanova",
    "vertex_ai", "bedrock", "cohere", "huggingface", "moonshot", "zai",
    "minimax", "volcengine", "dashscope", "nvidia_nim", "deepinfra",
    "hyperbolic", "nebius", "lambda", "github", "vllm", "lm_studio",
    "xinference", "wandb", "watsonx", "scaleway", "cloudflare_workers",
    "aiml", "novita", "nscale", "xiaomi_mimo", "siliconflow", "featherless",
    "anyscale", "databricks", "snowflake", "galadriel", "nano_gpt",
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
        seen = {}
        for index, field in enumerate(self.fields):
            if field.name in seen:
                raise PydanticCustomError("duplicate_field", "Duplicate field names at indices {first} and {duplicate}", {"first": seen[field.name], "duplicate": index})
            seen[field.name] = index
        return self


class ProjectSpec(StrictModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{1,49}$")
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=2000)
    entities: list[EntitySpec] = Field(min_length=1, max_length=8)
    unsupported_features: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def references_and_cycles(self) -> "ProjectSpec":
        indices = {}
        for index, entity in enumerate(self.entities):
            if entity.name in indices:
                raise PydanticCustomError("duplicate_entity", "Duplicate entity names at indices {first} and {duplicate}", {"first": indices[entity.name], "duplicate": index})
            indices[entity.name] = index
        edges: dict[str, list[str]] = {name: [] for name in indices}
        for index, entity in enumerate(self.entities):
            for field_index, field in enumerate(entity.fields):
                if field.kind == "reference":
                    if field.references not in edges:
                        raise PydanticCustomError("unknown_reference", "Unknown reference target at entities[{entity}].fields[{field}].references", {"entity": index, "field": field_index})
                    edges[entity.name].append(field.references)
        visiting: list[str] = []
        visited: set[str] = set()

        def visit(n: str) -> None:
            if n in visiting:
                cycle = [indices[node] for node in visiting[visiting.index(n):] + [n]]
                raise PydanticCustomError("reference_cycle", "References must be acyclic; cycle entity indices: {cycle}", {"cycle": cycle})
            if n in visited:
                return
            visiting.append(n)
            for target in edges[n]:
                visit(target)
            visiting.pop()
            visited.add(n)
        for name in indices:
            visit(name)
        return self

    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.model_dump()).encode()).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class ProjectInput(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    requirement: str = Field(min_length=5, max_length=16000)
    template_id: str = "fastapiadmin-pg-v1"


class MessageInput(StrictModel):
    content: str = Field(min_length=1, max_length=16000)


class LiteLLMOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout: int = Field(default=90, ge=10, le=180)
    num_retries: int = Field(default=0, ge=0, le=2)
    drop_params: bool = True
    top_p: float | None = Field(default=None, ge=0, le=1)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    seed: int | None = Field(default=None, ge=0, le=2147483647)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    aws_region_name: str | None = Field(default=None, pattern=r"^[a-z0-9-]{1,50}$")
    vertex_project: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9._:-]{1,100}$")
    vertex_location: str | None = Field(default=None, pattern=r"^[a-z0-9-]{1,60}$")
    organization: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,120}$")


class ProviderCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aws_access_key_id: str = Field(default="", max_length=256)
    aws_secret_access_key: str = Field(default="", max_length=4096)
    aws_session_token: str = Field(default="", max_length=16000)
    vertex_credentials: str = Field(default="", max_length=20000)

    @field_validator("vertex_credentials")
    @classmethod
    def service_account_only(cls, value: str) -> str:
        if value:
            data = json.loads(value)
            if not isinstance(data, dict) or data.get("type") != "service_account":
                raise ValueError("Only a service-account JSON document is accepted, never a file path")
            if data.get("token_uri") not in {None, "https://oauth2.googleapis.com/token"}:
                raise ValueError("Custom credential endpoints are not accepted")
            allowed = {"type", "project_id", "private_key_id", "private_key", "client_email", "client_id",
                       "auth_uri", "token_uri", "auth_provider_x509_cert_url", "client_x509_cert_url", "universe_domain"}
            if set(data) - allowed or data.get("universe_domain", "googleapis.com") != "googleapis.com":
                raise ValueError("Only standard Google service-account fields are supported")
            if not all(isinstance(data.get(key), str) and data[key] for key in ("client_email", "private_key", "project_id")):
                raise ValueError("Incomplete service-account credentials")
            data["token_uri"] = "https://oauth2.googleapis.com/token"
            # Canonical necessary fields only; certificate URLs are not needed for token exchange.
            value = json.dumps({key:data[key] for key in ("type", "project_id", "private_key_id", "private_key",
                                "client_email", "client_id", "token_uri") if key in data})
        return value


class ProviderInput(StrictModel):
    litellm_params: LiteLLMOptions = Field(default_factory=LiteLLMOptions)
    credentials: ProviderCredentials = Field(default_factory=ProviderCredentials)
    name: str = Field(min_length=1, max_length=80)
    provider: ProviderKind
    base_url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=4096)
    model: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    is_default: bool = False
    api_version: str = Field(default="", max_length=80, pattern=r"^[A-Za-z0-9.\-]*$")
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int = Field(default=6000, ge=1, strict=True)


class ProviderUpdate(StrictModel):
    litellm_params: LiteLLMOptions | None = None
    credentials: ProviderCredentials | None = None
    name: str | None = Field(default=None, min_length=1, max_length=80)
    provider: ProviderKind | None = None
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=4096)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    is_default: bool | None = None
    api_version: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9.\-]*$")
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, strict=True)


class DiscoverInput(StrictModel):
    provider: ProviderKind
    base_url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=4096)


class ClarifyInput(StrictModel):
    provider_id: str | None = Field(default=None, max_length=36)


class QuestionChoice(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    options: list[str] = Field(min_length=1, max_length=6)
    recommended: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def recommendation_is_an_option(self) -> "QuestionChoice":
        if any(not option.strip() or len(option) > 4000 for option in self.options):
            raise ValueError("Options must be nonempty and at most 4000 characters")
        if len(set(self.options)) != len(self.options) or self.recommended not in self.options:
            raise ValueError("Options must be unique and include the recommendation")
        return self


class ClarificationResult(StrictModel):
    ready: bool
    understanding: str = Field(min_length=1, max_length=4000)
    questions: list[str] = Field(default_factory=list, max_length=12)
    question_choices: list[QuestionChoice] = Field(default_factory=list, max_length=12)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=30)
    risks: list[str] = Field(default_factory=list, max_length=20)
    suggested_stack: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def ready_is_actionable(self) -> "ClarificationResult":
        choice_questions = [choice.question for choice in self.question_choices]
        if len(set(choice_questions)) != len(choice_questions) or any(q not in self.questions for q in choice_questions):
            raise ValueError("Question choices must refer to distinct current questions")
        if self.ready and self.questions:
            raise ValueError("A ready clarification cannot contain unanswered blocking questions")
        if self.ready and not self.acceptance_criteria:
            raise ValueError("A ready clarification needs explicit acceptance criteria")
        if not self.ready and not self.questions:
            raise ValueError("A non-ready clarification must ask at least one blocking question")
        return self


class RunInput(StrictModel):
    expected_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    provider_id: str | None = Field(default=None, max_length=36)
    # Backward-compatible field for older API clients. New UI uses provider_id only.
    provider: Literal["demo", "litellm"] | None = "demo"
    # Legacy raw /factory-api clients keep the original conservative defaults.
    # The new FastapiAdmin workbench sends the full-mode choices explicitly.
    use_serena: bool = False
    sandbox: Literal["static", "docker", "cube"] = "static"
    pipeline_mode: PipelineMode = "core"
    validation_level: Literal["source", "runtime"] = "source"
    provision_coder: bool = False
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


    @model_validator(mode="after")
    def runtime_requires_docker(self) -> "RunInput":
        if self.validation_level == "runtime" and (self.sandbox != "docker" or self.pipeline_mode != "core"):
            raise ValueError("运行验收需要 Docker 沙箱和 core 流水线")
        return self


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
        "unsupported_features": ["测试夹具不代表 AI 已分析自由文本需求。"]
    })

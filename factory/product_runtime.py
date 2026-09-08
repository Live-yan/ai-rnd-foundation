"""Deterministic CRUD runtime shared by generated products; never executes model-written code."""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict, Field, FiniteFloat, StrictBool, StrictInt, create_model
from sqlalchemy import (Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, MetaData,
                        String, Table, Text, and_, delete, func, insert, or_, select, update)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .schemas import EntitySpec, ProjectSpec

SQL_TYPES = {"string": lambda: String(255), "text": Text, "integer": Integer,
             "number": Float, "boolean": Boolean, "date": Date, "datetime": lambda: DateTime(timezone=True),
             "reference": Integer}
PY_TYPES = {"string": Annotated[str, Field(max_length=255)], "text": Annotated[str, Field(max_length=20000)],
            "integer": StrictInt, "number": FiniteFloat, "boolean": StrictBool,
            "date": date, "datetime": datetime, "reference": Annotated[StrictInt, Field(gt=0)]}


def build_metadata(spec: ProjectSpec | dict) -> MetaData:
    spec = ProjectSpec.model_validate(spec) if isinstance(spec, dict) else spec
    metadata = MetaData()
    for entity in spec.entities:
        columns = [Column("id", Integer, primary_key=True, autoincrement=True),
                   Column("owner_id", String(80), nullable=False, index=True),
                   Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now())]
        for field in entity.fields:
            args: list[Any] = [SQL_TYPES[field.kind]()]
            if field.kind == "reference":
                args.append(ForeignKey(f"biz_{field.references}.id", ondelete="RESTRICT"))
            columns.append(Column(field.name, *args, nullable=not field.required,
                                  index=field.kind == "reference"))
        Table(f"biz_{entity.name}", metadata, *columns)
    return metadata


def input_model(entity: EntitySpec, partial: bool = False):
    fields = {}
    for field in entity.fields:
        kind = PY_TYPES[field.kind]
        if partial or not field.required:
            fields[field.name] = (kind | None, None)
        else:
            fields[field.name] = (kind, ...)
    return create_model(f"{entity.name}_{'Patch' if partial else 'Create'}", __config__=ConfigDict(extra="forbid"), **fields)


def create_business_router(engine: Engine, spec: ProjectSpec | dict,
                           actor_dependency: Callable) -> APIRouter:
    spec = ProjectSpec.model_validate(spec) if isinstance(spec, dict) else spec
    metadata = build_metadata(spec)
    router = APIRouter(prefix="/business-api", tags=["Generated business"])

    @router.get("/schema")
    def schema(actor: str = Depends(actor_dependency)):
        return spec.model_dump()

    def add_entity(entity: EntitySpec) -> None:
        table = metadata.tables[f"biz_{entity.name}"]
        create_input, patch_input = input_model(entity), input_model(entity, partial=True)

        def owner_condition(actor: str):
            return table.c.owner_id == str(actor)

        def check_references(conn, values: dict, actor: str) -> None:
            for field in entity.fields:
                if field.name not in values:
                    continue
                if values[field.name] is None:
                    if field.required:
                        raise HTTPException(422, f"{field.name} may not be null")
                    continue
                if field.kind == "reference":
                    target = metadata.tables[f"biz_{field.references}"]
                    found = conn.execute(select(target.c.id).where(
                        target.c.id == values[field.name], target.c.owner_id == str(actor))).first()
                    if not found:
                        raise HTTPException(422, "Reference target is unavailable to this user")

        def public_row(row):
            value = dict(row)
            value.pop("owner_id", None)
            return value

        def list_items(offset: int = Query(0, ge=0, le=100000),
                       limit: int = Query(50, ge=1, le=200),
                       q: str = Query("", max_length=100), actor: str = Depends(actor_dependency)):
            where = owner_condition(actor)
            searchable = [table.c[f.name].contains(q, autoescape=True)
                          for f in entity.fields if f.kind in {"string", "text"}]
            if q and searchable:
                where = and_(where, or_(*searchable))
            with engine.begin() as conn:
                total = conn.scalar(select(func.count()).select_from(table).where(where))
                rows = conn.execute(select(table).where(where).order_by(table.c.id).offset(offset).limit(limit)).mappings()
                return {"items": [public_row(row) for row in rows], "total": total, "offset": offset, "limit": limit}

        def create_item(payload, actor: str = Depends(actor_dependency)):
            values = payload.model_dump()
            values["owner_id"] = str(actor)
            try:
                with engine.begin() as conn:
                    check_references(conn, values, actor)
                    row = conn.execute(insert(table).values(**values).returning(table)).mappings().one()
                    return public_row(row)
            except IntegrityError as exc:
                raise HTTPException(409, "Database constraint rejected the record") from exc
        create_item.__annotations__["payload"] = create_input

        def patch_item(item_id: int, payload, actor: str = Depends(actor_dependency)):
            values = payload.model_dump(exclude_unset=True)
            try:
                with engine.begin() as conn:
                    where = and_(table.c.id == item_id, owner_condition(actor))
                    if not conn.execute(select(table.c.id).where(where)).first():
                        raise HTTPException(404, "Record not found")
                    check_references(conn, values, actor)
                    if values:
                        conn.execute(update(table).where(where).values(**values))
                    return public_row(conn.execute(select(table).where(where)).mappings().one())
            except IntegrityError as exc:
                raise HTTPException(409, "Database constraint rejected the record") from exc
        patch_item.__annotations__["payload"] = patch_input

        def delete_item(item_id: int, actor: str = Depends(actor_dependency)):
            try:
                with engine.begin() as conn:
                    row = conn.execute(delete(table).where(table.c.id == item_id, owner_condition(actor)).returning(table.c.id)).first()
                    if not row:
                        raise HTTPException(404, "Record not found")
                return {"deleted": item_id}
            except IntegrityError as exc:
                raise HTTPException(409, "Delete dependent child records first") from exc

        prefix = f"/{entity.name}"
        router.add_api_route(prefix, list_items, methods=["GET"], name=f"list_{entity.name}")
        router.add_api_route(prefix, create_item, methods=["POST"], status_code=201, name=f"create_{entity.name}")
        router.add_api_route(prefix + "/{item_id}", patch_item, methods=["PATCH"], name=f"patch_{entity.name}")
        router.add_api_route(prefix + "/{item_id}", delete_item, methods=["DELETE"], name=f"delete_{entity.name}")

    for entity in spec.entities:
        add_entity(entity)
    return router

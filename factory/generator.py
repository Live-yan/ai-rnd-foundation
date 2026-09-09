"""Golden-template materialization and deterministic business extension."""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from .artifacts import build_architecture, build_openspec, put
from .config import ROOT
from .product_runtime import build_metadata, create_business_router
from .schemas import ProjectSpec
from .security import file_sha256, include_file

MANIFEST = json.loads((ROOT / 'templates/fastapiadmin/manifest.json').read_text(encoding='utf-8'))


def migration_source(spec: ProjectSpec) -> str:
    # A frozen migration: it contains literal columns and does not import the current model.
    meta = build_metadata(spec)
    by_name = {f'biz_{e.name}': e for e in spec.entities}
    lines = ['"""Initial generated business schema. Do not edit after applying."""',
             'from alembic import op', 'import sqlalchemy as sa', "revision = 'biz_0001'",
             'down_revision = None', 'branch_labels = None', 'depends_on = None', '', 'def upgrade():']
    types = {'string':'sa.String(255)', 'text':'sa.Text()', 'integer':'sa.Integer()', 'number':'sa.Float()',
             'boolean':'sa.Boolean()', 'date':'sa.Date()', 'datetime':'sa.DateTime(timezone=True)', 'reference':'sa.Integer()'}
    ordered = list(meta.sorted_tables)
    for table in ordered:
        entity = by_name[table.name]
        lines += [f'    op.create_table({table.name!r},',
                  "        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),",
                  "        sa.Column('owner_id', sa.String(80), nullable=False),",
                  "        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),"]
        for f in entity.fields:
            foreign = f', sa.ForeignKey("biz_{f.references}.id", ondelete="RESTRICT")' if f.kind == 'reference' else ''
            lines.append(f'        sa.Column({f.name!r}, {types[f.kind]}{foreign}, nullable={not f.required}),')
        lines.append('    )')
        from sqlalchemy.dialects.postgresql import dialect
        for index in sorted(table.indexes, key=lambda i: str(i.name)):
            index_name = dialect().identifier_preparer.format_index(index).strip(chr(34))
            names = [c.name for c in index.columns]
            lines.append(f'    op.create_index({index_name!r}, {table.name!r}, {names!r})')
    lines += ['', 'def downgrade():']
    for table in reversed(ordered):
        lines.append(f'    op.drop_table({table.name!r})')
    return '\n'.join(lines) + '\n'


def _generate_product(spec: ProjectSpec, upstream: Path, destination: Path,
                     *, diagrams_required: bool = True, test_fixture: bool = False) -> dict:
    from scripts.bootstrap import check_contract, copy_source, add_frontend_route
    check_contract(upstream)
    receipt = upstream / '.factory-upstream.json'
    if not test_fixture:
        if not receipt.is_file() or json.loads(receipt.read_text())['commit'] != MANIFEST['commit']:
            raise RuntimeError('Unverified upstream template: run the pinned bootstrap first')
    if destination.exists():
        old = destination / 'delivery/receipt.json'
        if old.is_file() and json.loads(old.read_text())['spec_digest'] == spec.digest():
            return json.loads(old.read_text())
        raise RuntimeError('Destination exists with a different or incomplete specification')
    stage = destination.with_name(destination.name + '.staging')
    if stage.exists():
        shutil.rmtree(stage)
    try:
        copy_source(upstream, stage)
        add_frontend_route(
            stage,
            'business',
            'BusinessConsole',
            ROOT / 'overlays/product/BusinessConsole.vue',
            title='业务管理',
            icon='ri:database-2-line',
        )
        put(stage, 'backend/business_runtime.py', (ROOT / 'factory/product_runtime.py').read_text().replace(
            'from .schemas import', 'from business_schema import'))
        put(stage, 'backend/business_schema.py', (ROOT / 'factory/schemas.py').read_text())
        put(stage, 'backend/business_spec.json', spec.model_dump_json(indent=2))
        for name in ['delivery_db.py', 'delivery_entry.py']:
            put(stage, 'backend/' + name, (ROOT / 'overlays/product' / name).read_text())
        for name in ['compose.yaml', 'Dockerfile.delivery']:
            put(stage, name, (ROOT / 'overlays/product' / name).read_text())
        for name in ['init_product.py','start_product.sh','run_local.py']:
            put(stage, 'scripts/' + name, (ROOT / 'overlays/product' / name).read_text())
        put(stage, 'scripts/verify_source.py', (ROOT / 'scripts/verify_source.py').read_text())
        put(stage, 'scripts/verify_business.py', (ROOT / 'scripts/verify_business.py').read_text())
        put(stage, '.dockerignore', '.git\n.venv\n**/.venv\n**/node_modules\n**/__pycache__\n.env\nbackend/env/.env.dev\nbackend/env/.env.prod\n')
        put(stage, '.gitignore', '.env\nbackend/env/.env.dev\nbackend/env/.env.prod\n.venv/\n**/.venv/\n**/node_modules/\n**/__pycache__/\n')
        put(stage, 'frontend/web/.env.production.example',
            'VITE_APP_ENV=prod\nVITE_ACCESS_MODE=mixed\nVITE_API_URL=/\nVITE_APP_TITLE=Generated Product\n')
        put(stage, 'backend/business-alembic.ini', '[alembic]\nscript_location = business_migrations\nprepend_sys_path = .\n')
        put(stage, 'backend/business_migrations/env.py',
            'from alembic import context\nfrom delivery_db import make_engine\n\n'
            'engine = make_engine()\nwith engine.connect() as connection:\n'
            '    context.configure(connection=connection, target_metadata=None, version_table="business_alembic_version")\n'
            '    with context.begin_transaction():\n        context.run_migrations()\n')
        put(stage, 'backend/business_migrations/versions/0001_business.py', migration_source(spec))
        put(stage, 'backend/business_migrations/script.py.mako',
            '"""${message}"""\nfrom alembic import op\nimport sqlalchemy as sa\nrevision = ${repr(up_revision)}\n'
            'down_revision = ${repr(down_revision)}\nbranch_labels = None\ndepends_on = None\n'
            'def upgrade():\n    ${upgrades if upgrades else "pass"}\n'
            'def downgrade():\n    ${downgrades if downgrades else "pass"}\n')
        put(stage, '.vscode/extensions.json', json.dumps({'recommendations': ['ms-python.python','Vue.volar','ms-azuretools.vscode-docker']}, indent=2))
        put(stage, '.vscode/settings.json', json.dumps({'python.defaultInterpreterPath': '${workspaceFolder}/backend/.venv/bin/python'}, indent=2))
        put(stage, '.vscode/tasks.json', json.dumps({'version':'2.0.0','tasks':[
            {'label':'Product: start dependencies','type':'shell','command':'docker compose up -d postgres redis','problemMatcher':[]},
            {'label':'Product: run backend','type':'shell','command':'uv run --project backend python scripts/run_local.py','problemMatcher':[]},
            {'label':'Product: business contract check','type':'shell','command':'uv run --project backend python scripts/verify_business.py','problemMatcher':[]}]}, indent=2))
        checks = build_architecture(stage, spec, diagrams_required=diagrams_required)
        build_openspec(stage, spec)
        # Export business OpenAPI without pretending this is the combined upstream admin OpenAPI.
        from fastapi import FastAPI
        from sqlalchemy import create_engine
        engine = create_engine('sqlite://')
        app = FastAPI(title=spec.title)
        app.include_router(create_business_router(engine, spec, lambda: 'openapi-export-only'))
        put(stage, 'docs/business-openapi.json', json.dumps(app.openapi(), ensure_ascii=False, indent=2))
        engine.dispose()
        put(stage, 'docs/ACCEPTANCE.md', acceptance(spec))
        put(stage, 'README_DELIVERY.md', readme(spec))
        put(stage, 'AGENTS.md', (ROOT / 'templates/fastapiadmin/ARCHITECTURE.md').read_text() +
            '\n## Generated product rules\nNever remove owner filtering or replace FastapiAdmin authentication. '
            'Business schema changes need new migrations, not edits to biz_0001.\n')
        put(stage, 'delivery/template-provenance.json', json.dumps(MANIFEST, indent=2, ensure_ascii=False))
        put(stage, 'delivery/approved-spec.json', spec.model_dump_json(indent=2))
        receipt_value = {'spec_digest': spec.digest(), 'template_commit': MANIFEST['commit'],
                         'architecture': checks, 'test_fixture': test_fixture,
                         'status': 'generated_not_full_stack_verified'}
        put(stage, 'delivery/receipt.json', json.dumps(receipt_value, indent=2, ensure_ascii=False))
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(destination)
        return receipt_value
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def acceptance(spec: ProjectSpec) -> str:
    return f'''# 业务验收：{spec.title}

这些是待执行的验收场景，不是已经通过的测试报告。结果记录在 delivery/quality.json。

1. 使用干净的 PostgreSQL 和 Redis 启动应用，确认上游初始化与 biz_0001 迁移成功。
2. 登录两个不同用户；每个用户新增记录，确认列表/更新/删除均不能访问另一个用户的数据。
3. 先创建父记录，再创建子记录；跨用户父记录 ID 应返回 422；有子记录时删除父记录应返回 409。
4. 验证所有必填字段、数字、日期、布尔值和未知字段拒绝行为。列表检查分页及搜索。
5. 浏览器刷新后数据仍在；应用重启后数据仍在；数据库备份后在新环境成功恢复。
6. 修改需求应产生新的源码包。不得覆盖已经部署项目的初始迁移或直接删库重建。
7. 人工逐条比对原需求与 unsupported_features，不得把 CRUD 页面视为审批/计费/设备采集的替代实现。

## 本次明确未支持的需求

''' + '\n'.join('- ' + x for x in spec.unsupported_features) + '\n'


def readme(spec: ProjectSpec) -> str:
    return f'''# {spec.title} · 生成项目启动说明

这是基于固定提交 FastapiAdmin 的实际源代码及类型化业务扩展，不依赖研发平台运行。
当前能力范围为 CRUD + 父子关联；请先阅读 delivery/quality.json 与 docs/ACCEPTANCE.md。

## 一、最简单的启动方式

在解压后的目录打开终端（Windows 建议 WSL Ubuntu）。安装 Docker Desktop 并启用 WSL 集成。

```bash
python3 scripts/init_product.py
docker compose up --build -d
docker compose logs -f app
```

浏览器打开 http://localhost:8010/api/v1/web/，按上游 README 的初始化账号说明登录，立刻修改初始密码。
然后从左侧菜单进入“业务管理”，或直接访问 http://localhost:8010/api/v1/web/#/business 。不要把此本地开发配置暴露到公网。
端口冲突时修改 compose.yaml 中左侧的 8010；数据库 55433、Redis 56380 也可能需要修改。
第一次构建需要下载上游锁定依赖和镜像，源码在 ZIP 中但依赖不是离线内置的。

## 二、在 VS Code 中开发

1. 打开整个解压目录；在 WSL 终端执行 `code .`。
2. 执行 `python3 scripts/init_product.py`；执行 `docker compose up -d postgres redis`。
3. 执行 `cd backend && uv sync && cd ..`。
4. 构建前端：`cd frontend/web && corepack pnpm install --frozen-lockfile`（没有锁文件时用 `pnpm install`），
   将 `.env.production.example` 复制为 `.env.production`，补充 `VITE_BASE_URL=/api/v1/web/` 和 `VITE_APP_BASE_API=/api/v1`，
   再执行 `pnpm exec vite build --mode production` 以生成自动导入类型声明，确认 `src/types/auto-imports.d.ts` 与 `src/types/components.d.ts` 已生成，最后执行 `pnpm exec vue-tsc --noEmit`。
5. 将 `frontend/web/dist` 复制到 `backend/dist`，回到项目根目录执行：
   `uv run --project backend python scripts/run_local.py`。
6. 在浏览器中打开上述地址。该脚本自动加载 backend/env/.env.dev，并先应用业务迁移。
7. 也可单独启动 Vite 热更新；需要为 `/business-api` 配置到 8010 的代理，不能只代理上游 API。

## 三、在 IDEA 中打开

打开整个项目目录，不要选择导入 Maven（这是 Python 项目）。使用支持 Python 的 JetBrains IDE/插件，
把解释器指定为 backend/.venv 中的 Python。IDE 不会替你安装 PostgreSQL、Redis、uv 或 Node。
初次仍按第二节在 IDE 终端执行命令。将来生成 Java 模板才使用 Maven/Gradle 导入。

## 四、文件在哪里

- backend/business_spec.json：已批准的结构化需求。
- backend/business_runtime.py：可信的通用 CRUD 实现；非模型自由编写的任意程序。
- backend/delivery_entry.py：原 FastapiAdmin 工厂 + 原认证 + 业务路由。
- backend/business_migrations：独立业务迁移，版本表 business_alembic_version。
- frontend/web/src/views/business/BusinessConsole.vue：业务页面。
- architecture/workspace.dsl：C4 架构源文件；architecture/er.svg：业务 ER 图。
- docs/business-openapi.json：仅业务路由的 OpenAPI；实际应用完整 API 以运行后的文档为准。
- openspec/changes/create-product：提案、设计、任务、规格；未做的验收任务保留未勾选。
- delivery：规格、来源、质量报告、文件哈希。

## 五、停止与保留数据

`docker compose stop` 停止服务并保留数据；`docker compose up -d` 重新启动。
`docker compose down` 删除容器但保留命名卷；不要随意使用 `down -v`，它会删除数据库卷。
`.env`、backend/env/.env.dev、日志、真实数据库备份不得上传 GitHub。

## 六、明确限制

''' + '\n'.join('- ' + x for x in spec.unsupported_features) + '\n'


def generate_product(spec: ProjectSpec, upstream: Path, destination: Path,
                     *, diagrams_required: bool = True, test_fixture: bool = False) -> dict:
    from .locking import artifact_lock
    with artifact_lock(destination.parent):
        return _generate_product(spec, upstream, destination, diagrams_required=diagrams_required, test_fixture=test_fixture)

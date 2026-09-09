"""Architecture Pack from the same approved schema used for application generation.
C4 is an architectural description, ER is the generated business schema (not DB reflection).
"""
from __future__ import annotations
import html
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path
from .schemas import ProjectSpec
from .diagram_assets import embed_svg_images


def put(root: Path, name: str, text: str):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def dsl_quote(value: str) -> str:
    # Only allow data, never a DSL directive or external include.
    value = ''.join(' ' if ord(c) < 32 else c for c in value)
    return '"' + value.replace('\\', '/').replace('"', "'") + '"'


def c4_dsl(spec: ProjectSpec) -> str:
    lines = [f'workspace {dsl_quote(spec.title)} "Generated architecture description" {{',
             '  model {', '    user = person "User" "Authenticated application user"',
             f'    system = softwareSystem {dsl_quote(spec.title)} "FastapiAdmin-based generated product" {{',
             '      web = container "Web UI" "Forms, lists and administration" "Vue 3 / TypeScript"',
             '      api = container "Application API" "Authentication and business endpoints" "FastAPI / Python" {',
             '        auth = component "Authentication adapter" "Reuses upstream JWT, Redis session and live user checks" "FastapiAdmin"']
    for entity in spec.entities:
        lines.append(f'        c_{entity.name} = component {dsl_quote(entity.label)} "Typed owner-scoped CRUD" "SQLAlchemy Core"')
    lines += ['      }', '      db = container "Database" "Admin and generated business data" "PostgreSQL"',
              '      redis = container "Session cache" "Upstream sessions and caching" "Redis"', '    }',
              '    user -> web "Uses" "HTTP (local development)"',
              '    web -> api "Calls authenticated APIs" "HTTP / JSON"',
              '    api -> db "Reads and writes" "SQL"',
              '    api -> redis "Validates sessions" "Redis protocol"',
              '    auth -> db "Checks current user" "SQL"', '    auth -> redis "Checks session" "Redis protocol"']
    for entity in spec.entities:
        lines += [f'    c_{entity.name} -> auth "Requires identity"',
                  f'    c_{entity.name} -> db "CRUD biz_{entity.name}" "SQL"']
    lines += ['  }', '  views {', '    systemContext system "C1" {', '      include *', '      autoLayout lr', '    }',
              '    container system "C2" {', '      include *', '      autoLayout lr', '    }',
              '    component api "C3" {', '      include *', '      autoLayout lr', '    }', '  }', '}']
    return '\n'.join(lines) + '\n'


def er_dot(spec: ProjectSpec) -> str:
    lines = ['digraph ER {', '  graph [rankdir=LR, charset="UTF-8"];',
             '  node [shape=plain, fontname="sans-serif"];', '  edge [fontname="sans-serif"];']
    for entity in spec.entities:
        fields = ['id : integer PK', 'owner_id : string (private scope)', 'created_at : timestamp'] + [
            f'{f.name} : {f.kind}' + (' NOT NULL' if f.required else ' NULL') for f in entity.fields]
        label = '<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0"><TR><TD><B>biz_' + entity.name + '</B></TD></TR>'
        label += ''.join(f'<TR><TD ALIGN="LEFT">{html.escape(field)}</TD></TR>' for field in fields) + '</TABLE>'
        lines.append(f'  {entity.name} [label=<{label}>];')
        for f in entity.fields:
            if f.kind == 'reference':
                lines.append(f'  {f.references} -> {entity.name} [label="{f.name}", arrowhead=crow, arrowtail=tee, dir=both];')
    return '\n'.join(lines + ['}']) + '\n'


def build_architecture(root: Path, spec: ProjectSpec, *, diagrams_required: bool = True) -> dict:
    output = root / 'architecture'
    output.mkdir(parents=True, exist_ok=True)
    put(root, 'architecture/workspace.dsl', c4_dsl(spec))
    put(root, 'architecture/er.dot', er_dot(spec))
    result = {'c4_dsl': 'generated_not_parser_validated', 'er_source': 'approved_business_metadata_not_live_database'}
    if shutil.which('dot'):
        subprocess.run(['dot', '-Tsvg', str(output / 'er.dot'), '-o', str(output / 'er.svg')],
                       check=True, timeout=30, capture_output=True)
        result['er_svg'] = 'rendered'
    else:
        raise RuntimeError('Graphviz dot is required for ER export; install graphviz')
    mermaid = ['erDiagram']
    for e in spec.entities:
        mermaid += [f'  biz_{e.name} {{', '    int id PK', '    string owner_id', '    datetime created_at']
        for f in e.fields:
            kind = {'reference': 'int', 'integer': 'int', 'number': 'float', 'text': 'string'}.get(f.kind, f.kind)
            mermaid.append(f'    {kind} {f.name}' + (' FK' if f.kind == 'reference' else ''))
        mermaid.append('  }')
        for f in e.fields:
            if f.kind == 'reference':
                parent = '||' if f.required else '|o'
                mermaid.append(f'  biz_{f.references} {parent}--o{{ biz_{e.name} : {f.name}')
    put(root, 'architecture/er.mmd', '\n'.join(mermaid) + '\n')
    dictionary = ['# 数据字典', '', '仅描述本次生成的 biz_ 业务表；不声称是线上数据库反射，也不包含上游管理表。', '']
    for e in spec.entities:
        dictionary += [f'## biz_{e.name} / {e.label}', '', '|字段|类型|必填|引用|', '|---|---|---|---|',
                       '|id|integer 主键|是|-|', '|owner_id|string(80)，服务端从登录身份写入|是|-|',
                       '|created_at|timestamp，数据库默认时间|是|-|']
        dictionary += [f'|{f.name}|{f.kind}|{"是" if f.required else "否"}|{f.references or "-"}|' for f in e.fields]
        dictionary.append('')
    put(root, 'docs/DATA_DICTIONARY.md', '\n'.join(dictionary))
    # Execute trusted code only, not a Python program supplied by an LLM.
    source = '''from diagrams import Diagram
from diagrams.onprem.client import Users
from diagrams.onprem.compute import Server
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.inmemory import Redis

def render(filename):
    with Diagram("Generated product deployment", filename=str(filename), outformat="svg", show=False):
        user = Users("User")
        web = Server("Vue / FastAPI")
        user >> web
        web >> PostgreSQL("PostgreSQL")
        web >> Redis("Sessions")
    embed_svg_images(Path(str(filename) + ".svg"))

if __name__ == "__main__":
    from pathlib import Path
    render(Path(__file__).with_name("deployment"))
'''
    source = Path(__file__).with_name('diagram_assets.py').read_text() + '\n' + source
    put(root, 'architecture/deployment.py', source)
    try:
        from diagrams import Diagram
        from diagrams.onprem.client import Users
        from diagrams.onprem.compute import Server
        from diagrams.onprem.database import PostgreSQL
        from diagrams.onprem.inmemory import Redis
        with Diagram('Generated product deployment', filename=str(output / 'deployment'), outformat='svg', show=False):
            user = Users('User'); web = Server('Vue / FastAPI')
            user >> web
            web >> PostgreSQL('PostgreSQL')
            web >> Redis('Sessions')
        embed_svg_images(output / 'deployment.svg')
        result['diagrams'] = 'rendered_portable_svg'
    except ImportError:
        if diagrams_required:
            raise RuntimeError('The diagrams dependency is required; run uv sync')
        result['diagrams'] = 'not_run_dependency_missing'
    return result


def build_openspec(root: Path, spec: ProjectSpec, *, generated: bool = True, clarification: dict | None = None) -> None:
    put(root, 'openspec/config.yaml', 'schema: spec-driven\ncontext: |\n  FastapiAdmin, uv, PostgreSQL, Vue3.\n  Generate bounded CRUD, never claim unsupported business rules are complete.\n')
    base = 'openspec/changes/create-product'
    put(root, base + '/.openspec.yaml', f'schema: spec-driven\ncreated: {date.today().isoformat()}\n')
    put(root, base + '/proposal.md', f'# Change: Create {spec.title}\n\n## Why\n\n{spec.summary}\n\n'
        '## What Changes\n\n- Add owner-scoped generated business tables and routes.\n- Add Vue business console and architecture exports.\n\n'
        '## Capabilities\n\n### New Capabilities\n- `generated-business`: Typed CRUD and access isolation.\n\n'
        '### Modified Capabilities\nNone.\n\n## Impact\nNew biz_ tables. Existing FastapiAdmin authentication stays intact.\n')
    put(root, base + '/design.md', '# Design\n\nUse an approved ProjectSpec, deterministic SQLAlchemy runtime, FastapiAdmin authentication, '
        'versioned Alembic migrations and the generic Vue console. No arbitrary generated Python is executed by the platform.\n\n'
        '## Non-goals\n' + '\n'.join('- ' + x for x in spec.unsupported_features) + '\n')
    put(root, base + '/tasks.md', '# Implementation Tasks\n\n## 1. Generate the scaffold\n'
        '- [x] 1.1 Emit the approved business schema and trusted CRUD runtime\n'
        '- [x] 1.2 Emit architecture sources and delivery configuration\n'
        '- [ ] 1.3 Start the full PostgreSQL/Redis/application stack in a clean environment\n'
        '- [ ] 1.4 Test authentication, UI interactions and all business acceptance scenarios\n'
        '- [ ] 1.5 Complete security review before exposing to external users\n')
    put(root, base + '/specs/generated-business/spec.md',
        '## ADDED Requirements\n\n### Requirement: Owner-scoped CRUD\n'
        'The system SHALL restrict generated business records to the authenticated owner.\n\n'
        '#### Scenario: One user reads records\n- **GIVEN** two authenticated users each own records\n'
        '- **WHEN** one user lists a generated entity\n- **THEN** only their own records are returned\n\n'
        '### Requirement: Reference validation\nThe system SHALL reject references to records not owned by the current user.\n\n'
        '#### Scenario: A cross-owner reference is submitted\n- **WHEN** a user submits another user\'s parent record ID\n'
        '- **THEN** the request is rejected without disclosing the parent record\n\n'
        '### Requirement: Honest delivery status\nThe system SHALL distinguish scaffold checks from full deployment acceptance.\n\n'
        '#### Scenario: Source checks pass\n- **WHEN** only source checks have completed\n'
        '- **THEN** the result remains a scaffold and full deployment acceptance is reported as not run\n')
    put(root, 'openspec/specs/.gitkeep', '')
    tasks = {'schema_version': 1, 'tasks': [
        {'id': 'generate-schema', 'depends_on': [], 'executor': 'trusted_factory'},
        {'id': 'generate-code', 'depends_on': ['generate-schema'], 'executor': 'trusted_factory'},
        {'id': 'export-architecture', 'depends_on': ['generate-code'], 'executor': 'trusted_factory'},
        {'id': 'validate', 'depends_on': ['export-architecture'], 'executor': 'fixed_verifier'},
        {'id': 'package', 'depends_on': ['validate'], 'executor': 'trusted_factory'}],
        'note': 'Explicit platform DAG; OpenSpec Markdown checkboxes are not parsed as executable commands.'}
    put(root, 'docs/tasks.dag.json', json.dumps(tasks, indent=2, ensure_ascii=False))

    tasks_path = root / base / "tasks.md"
    if not generated:
        tasks_path.write_text(tasks_path.read_text(encoding="utf-8").replace("- [x]", "- [ ]"), encoding="utf-8")
    if clarification:
        brief = "# 已澄清需求与验收基线\n\n" + str(clarification.get("understanding", "")) + "\n"
        for key, title in [("acceptance_criteria", "待执行的验收标准"), ("assumptions", "假设"), ("risks", "风险")]:
            brief += "\n## " + title + "\n" + "\n".join("- " + str(x) for x in clarification.get(key, [])) + "\n"
        put(root, base + "/requirements.md", brief)

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
    # Model labels are data, not directives or environment-variable substitutions.
    import unicodedata
    value = ''.join(' ' if unicodedata.category(c).startswith('C') or c in {'\u2028', '\u2029'} else c for c in value)
    value = value.replace('\\', '/').replace('"', "'").replace('${', '$ {')
    return '"' + value + '"'


def c4_dsl(spec: ProjectSpec, *, template_id: str = 'fastapiadmin-pg-v1') -> str:
    java = template_id == 'yudao-cloud-mini-antd-v1'
    template, api, database, runtime = ('YuDao Cloud Mini', 'Spring Boot / Java 17', 'MySQL', 'JDBC') if java else ('FastapiAdmin', 'FastAPI / Python', 'PostgreSQL', 'SQLAlchemy Core')
    # Use explicit property lines instead of positional optional arguments. This
    # keeps the generated DSL unambiguous and leaves all labels inside quotes.
    lines = ['workspace {', f'  name {dsl_quote(spec.title)}',
             '  description "Generated architecture description"', '  model {',
             '    user = person "User"',
             f'    product = softwareSystem {dsl_quote(spec.title)} {{',
             f'      description "{template}-based generated product"',
             '      web = container "Web UI" {',
             '        description "Forms, lists and administration"',
             '        technology "Vue 3 / TypeScript"', '      }',
             '      api = container "Application API" {',
             '        description "Authentication and business endpoints"',
             f'        technology "{api}"',
             '        auth = component "Authentication adapter" {',
             '          description "Reuses upstream JWT, Redis session and live user checks"',
             f'          technology "{template}"', '        }']
    for entity in spec.entities:
        # Labels need not be unique in ProjectSpec, but C4 component names must be.
        lines += [f'        c_{entity.name} = component {dsl_quote(entity.label + " (" + entity.name + ")")} {{',
                  '          description "Typed owner-scoped CRUD"',
                  f'          technology "{runtime}"', '        }']
    lines += ['      }', '      db = container "Database" {',
              '        description "Admin and generated business data"',
              f'        technology "{database}"', '      }',
              '      redis = container "Session cache" {',
              '        description "Upstream sessions and caching"',
              '        technology "Redis"', '      }', '    }',
              '    user -> web "Uses" "HTTP (local development)"',
              '    web -> api "Calls authenticated APIs" "HTTP / JSON"',
              '    api -> db "Reads and writes" "SQL"',
              '    api -> redis "Validates sessions" "Redis protocol"',
              '    auth -> db "Checks current user" "SQL"',
              '    auth -> redis "Checks session" "Redis protocol"']
    for entity in spec.entities:
        lines += [f'    c_{entity.name} -> auth "Requires identity"',
                  f'    c_{entity.name} -> db "CRUD {"rnd_biz_" if java else "biz_"}{entity.name}" "SQL"']
    lines += ['  }', '  views {', '    systemContext product "C1" {',
              '      include *', '      autoLayout lr', '    }',
              '    container product "C2" {', '      include *', '      autoLayout lr', '    }',
              '    component api "C3" {', '      include *', '      autoLayout lr', '    }', '  }', '}']
    return '\n'.join(lines) + '\n'


def er_dot(spec: ProjectSpec, *, template_id: str = 'fastapiadmin-pg-v1') -> str:
    java = template_id == 'yudao-cloud-mini-antd-v1'
    prefix = 'rnd_biz_' if java else 'biz_'
    lines = ['digraph ER {', '  graph [rankdir=LR, charset="UTF-8"];',
             '  node [shape=plain, fontname="sans-serif"];', '  edge [fontname="sans-serif"];']
    for entity in spec.entities:
        fields = (['id : bigint PK', 'tenant_id : bigint', 'owner_id : bigint (private scope)', 'created_at : timestamp', 'updated_at : timestamp'] if java else ['id : integer PK', 'owner_id : string (private scope)', 'created_at : timestamp']) + [
            f'{f.name} : {f.kind}' + (' NOT NULL' if f.required else ' NULL') for f in entity.fields]
        label = '<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0"><TR><TD><B>' + prefix + entity.name + '</B></TD></TR>'
        label += ''.join(f'<TR><TD ALIGN="LEFT">{html.escape(field)}</TD></TR>' for field in fields) + '</TABLE>'
        lines.append(f'  {entity.name} [label=<{label}>];')
        for f in entity.fields:
            if f.kind == 'reference':
                lines.append(f'  {f.references} -> {entity.name} [label="{f.name}", arrowhead=crow, arrowtail=tee, dir=both];')
    return '\n'.join(lines + ['}']) + '\n'


def build_architecture(root: Path, spec: ProjectSpec, *, diagrams_required: bool = True,
                       template_id: str = 'fastapiadmin-pg-v1') -> dict:
    java = template_id == 'yudao-cloud-mini-antd-v1'
    prefix = 'rnd_biz_' if java else 'biz_'
    output = root / 'architecture'
    output.mkdir(parents=True, exist_ok=True)
    put(root, 'architecture/workspace.dsl', c4_dsl(spec, template_id=template_id))
    put(root, 'architecture/er.dot', er_dot(spec, template_id=template_id))
    result = {'c4_dsl': 'generated_not_parser_validated', 'er_source': 'approved_business_metadata_not_live_database'}
    if shutil.which('dot'):
        subprocess.run(['dot', '-Tsvg', str(output / 'er.dot'), '-o', str(output / 'er.svg')],
                       check=True, timeout=30, capture_output=True)
        result['er_svg'] = 'rendered'
    else:
        raise RuntimeError('Graphviz dot is required for ER export; install graphviz')
    mermaid = ['erDiagram']
    for e in spec.entities:
        mermaid += [f'  {prefix}{e.name} {{', '    int id PK', '    int owner_id' if java else '    string owner_id', '    datetime created_at']
        if java:
            mermaid += ['    int tenant_id', '    datetime updated_at']
        for f in e.fields:
            kind = {'reference': 'int', 'integer': 'int', 'number': 'float', 'text': 'string'}.get(f.kind, f.kind)
            mermaid.append(f'    {kind} {f.name}' + (' FK' if f.kind == 'reference' else ''))
        mermaid.append('  }')
        for f in e.fields:
            if f.kind == 'reference':
                parent = '||' if f.required else '|o'
                mermaid.append(f'  {prefix}{f.references} {parent}--o{{ {prefix}{e.name} : {f.name}')
    put(root, 'architecture/er.mmd', '\n'.join(mermaid) + '\n')
    dictionary = ['# 数据字典', '', '仅描述本次生成的 biz_ 业务表；不声称是线上数据库反射，也不包含上游管理表。', '']
    for e in spec.entities:
        dictionary += [f'## {prefix}{e.name} / {e.label}', '', '|字段|类型|必填|引用|', '|---|---|---|---|',
                       '|id|bigint 主键|是|-|' if java else '|id|integer 主键|是|-|', '|owner_id|' + ('bigint' if java else 'string(80)') + '，服务端从登录身份写入|是|-|',
                       '|created_at|timestamp，数据库默认时间|是|-|']
        if java:
            dictionary += ['|tenant_id|bigint，从登录租户写入|是|-|', '|updated_at|timestamp UTC|是|-|']
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
    if java:
        source = source.replace('PostgreSQL', 'MySQL').replace('Vue / FastAPI', 'Vue / Spring Boot')
    source = Path(__file__).with_name('diagram_assets.py').read_text() + '\n' + source
    put(root, 'architecture/deployment.py', source)
    try:
        from diagrams import Diagram
        from diagrams.onprem.client import Users
        from diagrams.onprem.compute import Server
        from diagrams.onprem.database import PostgreSQL, MySQL
        from diagrams.onprem.inmemory import Redis
        with Diagram('Generated product deployment', filename=str(output / 'deployment'), outformat='svg', show=False):
            user = Users('User'); web = Server('Vue / Spring Boot' if java else 'Vue / FastAPI')
            user >> web
            web >> (MySQL('MySQL') if java else PostgreSQL('PostgreSQL'))
            web >> Redis('Sessions')
        embed_svg_images(output / 'deployment.svg')
        result['diagrams'] = 'rendered_portable_svg'
    except ImportError:
        if diagrams_required:
            raise RuntimeError('The diagrams dependency is required; run uv sync')
        result['diagrams'] = 'not_run_dependency_missing'
    return result


def build_openspec(root: Path, spec: ProjectSpec, *, generated: bool = True, clarification: dict | None = None,
                   template_id: str = 'fastapiadmin-pg-v1') -> None:
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
    if template_id == 'yudao-cloud-mini-antd-v1':
        for relative in ('openspec/config.yaml', base + '/proposal.md', base + '/design.md', base + '/tasks.md'):
            path = root / relative
            text = path.read_text(encoding='utf-8')
            for old, new in [('FastapiAdmin', 'YuDao Cloud Mini'), ('PostgreSQL', 'MySQL'), ('SQLAlchemy', 'JDBC'),
                             ('Alembic migrations', 'SQL initialization'), ('uv,', 'Java 17, Maven,'),
                             ('generated Python', 'generated code'), ('biz_ tables', 'rnd_biz_ tables')]:
                text = text.replace(old, new)
            path.write_text(text, encoding='utf-8')
    if not generated:
        tasks_path.write_text(tasks_path.read_text(encoding="utf-8").replace("- [x]", "- [ ]"), encoding="utf-8")
    if clarification:
        brief = "# 已澄清需求与验收基线\n\n" + str(clarification.get("understanding", "")) + "\n"
        for key, title in [("acceptance_criteria", "待执行的验收标准"), ("assumptions", "假设"), ("risks", "风险")]:
            brief += "\n## " + title + "\n" + "\n".join("- " + str(x) for x in clarification.get(key, [])) + "\n"
        put(root, base + "/requirements.md", brief)

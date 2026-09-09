"""Stdlib-only SOURCE verification. Never executes project code or installs packages."""
import ast
import json
from pathlib import Path


def verify(root: Path) -> dict:
    count = 0
    for path in root.rglob('*.py'):
        if any(p in {'.venv', '.git', 'node_modules', '__pycache__'} for p in path.parts):
            continue
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path.relative_to(root)))
        count += 1
    spec = json.loads((root / 'backend/business_spec.json').read_text(encoding='utf-8'))
    for required in ['backend/delivery_entry.py', 'backend/business_runtime.py', 'architecture/workspace.dsl',
                     'architecture/er.svg', 'README_DELIVERY.md', 'compose.yaml']:
        if not (root / required).is_file():
            raise ValueError('Missing required artifact: ' + required)
    return {'source_ast': 'passed', 'python_files': count, 'entity_count': len(spec['entities']),
            'full_stack': 'not_run', 'ui_build': 'not_run', 'postgres_integration': 'not_run'}


if __name__ == '__main__':
    print(json.dumps(verify(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))

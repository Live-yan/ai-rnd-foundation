"""Idempotent local tool defaults; never overwrite an existing nonempty setting or generate model keys."""
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {
    'FACTORY_CODER_URL': 'http://coder:7080',
    'FACTORY_CODER_BROWSER_URL': 'http://localhost:7080',
    'FACTORY_CODER_FACTORY_URL': 'http://api:8000',
    'FACTORY_PUBLIC_URL': 'http://localhost:8000',
    'CODER_ACCESS_URL': 'http://localhost:7080',
}


def apply(path: Path) -> list[str]:
    if not path.is_file():
        raise RuntimeError('Run scripts/init_env.py first')
    if path.is_symlink():
        raise RuntimeError("Refusing to replace a symlinked .env; edit the real configuration explicitly")
    text = path.read_text(encoding='utf-8')
    rows = text.splitlines()
    changed = []
    for key, value in DEFAULTS.items():
        found = next((i for i, line in enumerate(rows) if line.startswith(key + '=')), None)
        if found is None:
            rows.append(key + '=' + value); changed.append(key)
        elif rows[found].split('=', 1)[1].strip() in {'', '""', "''"}:
            rows[found] = key + '=' + value; changed.append(key)
    if changed:
        path.write_text('\n'.join(rows) + '\n', encoding='utf-8')
        path.chmod(0o600)
    return changed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', type=Path, default=ROOT / '.env')
    args = parser.parse_args()
    print('Added empty defaults: ' + ', '.join(apply(args.env)))
    print('No model API keys, OAuth tokens, Cube templates, Coder tokens or administrator IDs were invented.')

"""Fetch a pinned upstream and assemble a real FastapiAdmin host; stdlib only.
No credentials are required for the public template. This is intentionally an ONLINE bootstrap.
"""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'templates/fastapiadmin/manifest.json').read_text(encoding='utf-8'))
OMIT = {'.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', '.ruff_cache', 'logs', 'dist'}


def run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stderr[-1800:]}')
    return result.stdout.strip()


def copy_source(source: Path, destination: Path) -> None:
    def ignore(folder, names):
        return [n for n in names if n in OMIT or Path(folder, n).is_symlink()
                or (n.startswith('.env') and not n.endswith('.example'))
                or n.endswith(('.key', '.pem', '.pyc'))]
    shutil.copytree(source, destination, ignore=ignore)


def frontend_public_base() -> str:
    root_path = str(MANIFEST['root_path']).rstrip('/')
    frontend_mount = '/' + str(MANIFEST['frontend_mount']).strip('/')
    expected = f'{root_path}{frontend_mount}/'
    configured = str(MANIFEST['frontend_public_base'])
    if configured != expected:
        raise RuntimeError(
            f'Invalid template frontend_public_base: expected {expected!r}, got {configured!r}'
        )
    return configured


def check_contract(source: Path) -> None:
    frontend_public_base()
    for rel in MANIFEST['required_paths']:
        if not (source / rel).is_file():
            raise RuntimeError(f'Upstream contract changed/missing: {rel}')
    router = (source / 'frontend/web/src/router/index.ts').read_text(encoding='utf-8')
    if 'export const router' not in router:
        raise RuntimeError('Unsupported upstream router entry; do not patch blindly')


def add_route(target: Path, name: str, component_name: str, source: Path) -> None:
    view_dir = target / f'frontend/web/src/views/{name}'
    view_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, view_dir / f'{component_name}.vue')
    router_path = target / 'frontend/web/src/router/index.ts'
    text = router_path.read_text(encoding='utf-8')
    marker = f'// AI-RND-EXTENSION:{name}:v1'
    if marker not in text:
        text += f'\n{marker}\nrouter.addRoute({{\n  path: "/{name}",\n  name: "rnd-{name}",\n  component: () => import("@/views/{name}/{component_name}.vue"),\n  meta: {{ title: "{name}", hidden: true }},\n}});\n'
        router_path.write_text(text, encoding='utf-8')


def fetch_upstream(target: Path) -> None:
    if target.exists():
        actual = run(['git', 'rev-parse', 'HEAD'], target)
        if actual != MANIFEST['commit']:
            raise RuntimeError('Existing .vendor commit differs. Preserve it and use a fresh directory.')
        if run(['git', 'status', '--porcelain', '--untracked-files=no'], target):
            raise RuntimeError('Pristine template contains tracked modifications; refusing to reuse it.')
        check_contract(target)
        return
    stage = target.with_name(target.name + '.incoming')
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    try:
        run(['git', 'init'], stage)
        run(['git', 'remote', 'add', 'origin', MANIFEST['upstream']], stage)
        run(['git', 'fetch', '--depth', '1', 'origin', MANIFEST['commit']], stage)
        run(['git', 'checkout', '--detach', 'FETCH_HEAD'], stage)
        if run(['git', 'rev-parse', 'HEAD'], stage) != MANIFEST['commit']:
            raise RuntimeError('Upstream commit verification failed')
        check_contract(stage)
        (stage / '.factory-upstream.json').write_text(json.dumps(MANIFEST, indent=2), encoding='utf-8')
        stage.rename(target)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def assemble(source: Path, destination: Path, *, replace: bool = False) -> None:
    check_contract(source)
    if destination.exists():
        if not replace:
            raise RuntimeError('runtime already exists. Use --replace-runtime only after saving local edits.')
        shutil.rmtree(destination)
    copy_source(source, destination)
    add_route(destination, 'factory', 'FactoryConsole', ROOT / 'overlays/platform/FactoryConsole.vue')
    # Build-only configuration: no credentials and no cross-origin API.
    (destination / 'frontend/web/.env.production').write_text(
        'VITE_APP_ENV=prod\nVITE_APP_TITLE=AI R&D Factory\n'
        f'VITE_BASE_URL={frontend_public_base()}\n'
        f'VITE_APP_BASE_API={MANIFEST["root_path"]}\n'
        'VITE_API_BASE_URL=http://127.0.0.1:8000\nVITE_DROP_CONSOLE=true\n', encoding='utf-8')
    print(f'Assembled: {destination}\nPinned upstream: {MANIFEST["commit"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replace-runtime', action='store_true')
    parser.add_argument('--fetch-only', action='store_true')
    args = parser.parse_args()
    source = ROOT / '.vendor/FastapiAdmin'
    fetch_upstream(source)
    if not args.fetch_only:
        assemble(source, ROOT / 'runtime/FastapiAdmin', replace=args.replace_runtime)


if __name__ == '__main__':
    main()

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
    patch_frontend_runtime(destination)


def patch_frontend_runtime(target: Path) -> None:
    """Repair pinned upstream runtime bugs in assembled copies, never the pristine source."""
    patches = [
        (
            'frontend/web/src/router/route-loader.ts',
            '  private handleFirstLevelLeaf(route: AppRouteRecord): Record<string, any> {\n',
            '  private handleFirstLevelLeaf(route: AppRouteRecord): Record<string, any> | null {\n'
            '    // AI-RND: RouteRegistry already mounts shell children under the root Layout.\n'
            '    if (this.options.shellChild) return this.buildLeafRoute(route, 0);\n',
        ),
        (
            'frontend/web/src/utils/sys/index.ts',
            'fetch(`/?_t=${Date.now()}`, { cache: "no-store" })',
            'fetch(`${import.meta.env.BASE_URL}?_t=${Date.now()}`, { cache: "no-store" })',
        ),
        (
            'frontend/web/src/router/route-loader.ts',
            '      redirect: fullMenuPath,\n',
            '      // AI-RND: redirect by child name; its URL stays at the menu path.\n'
            '      redirect: { name: `${String(route.name) || firstSegment}Child` },\n',
        ),
        (
            'frontend/web/src/router/route-loader.ts',
            '          path: fullMenuPath.replace(/^\\//, ""),\n',
            '          path: fullMenuPath,\n',
        ),
        (
            'frontend/web/src/utils/sse/index.ts',
            'export function httpEndpoint(endpoint: string): string {\n'
            '  return endpoint.replace(/^ws/, "http");\n}',
            'export function httpEndpoint(endpoint?: string): string {\n'
            '  // AI-RND: production is same-origin unless an endpoint is configured.\n'
            '  return (endpoint || window.location.origin).replace(/^ws/, "http");\n}',
        ),
    ]
    for relative, old, new in patches:
        path = target / relative
        text = path.read_text(encoding='utf-8')
        if new in text:
            continue
        if text.count(old) != 1:
            raise RuntimeError(f'Upstream frontend patch contract changed: {relative}')
        path.write_text(text.replace(old, new, 1), encoding='utf-8')


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
    menu_processor = (source / 'frontend/web/src/router/MenuProcessor.ts').read_text(encoding='utf-8')
    if 'export const builtinFrontendRoutes: AppRouteRecord[] = [];' not in menu_processor:
        raise RuntimeError('Unsupported upstream builtinFrontendRoutes contract; do not patch blindly')


def add_frontend_route(
    target: Path,
    name: str,
    component_name: str,
    source: Path,
    *,
    title: str,
    icon: str = 'ri:code-box-line',
) -> None:
    """Install one first-class mixed-mode route (used by generated products and tests)."""
    view_dir = target / f'frontend/web/src/views/{name}'
    view_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, view_dir / f'{component_name}.vue')

    menu_path = target / 'frontend/web/src/router/MenuProcessor.ts'
    text = menu_path.read_text(encoding='utf-8')
    marker = f'// AI-RND-FRONTEND-ROUTE:{name}:v2'
    if marker in text:
        return

    needle = 'export const builtinFrontendRoutes: AppRouteRecord[] = [];'
    if needle not in text:
        raise RuntimeError('builtinFrontendRoutes extension point changed; refusing to patch blindly')

    route = (
        f'{marker}\n'
        'export const builtinFrontendRoutes: AppRouteRecord[] = [\n'
        '  {\n'
        f'    path: {json.dumps("/" + name, ensure_ascii=False)},\n'
        f'    name: {json.dumps("rnd-" + name, ensure_ascii=False)},\n'
        f'    component: {json.dumps(name + "/" + component_name, ensure_ascii=False)},\n'
        '    meta: {\n'
        f'      title: {json.dumps(title, ensure_ascii=False)},\n'
        f'      icon: {json.dumps(icon, ensure_ascii=False)},\n'
        '      hidden: false,\n'
        '      isHide: false,\n'
        '      keepAlive: true,\n'
        '    },\n'
        '  },\n'
        '];'
    )
    menu_path.write_text(text.replace(needle, route, 1), encoding='utf-8')


def install_factory_frontend(target: Path) -> None:
    """Install the FastapiAdmin-native AI R&D workbench as three menu routes plus a typed API module."""
    files = [
        ('factory', 'FactoryConsole.vue', ROOT / 'overlays/platform/FactoryConsole.vue'),
        ('factory-providers', 'ProviderManager.vue', ROOT / 'overlays/platform/ProviderManager.vue'),
        ('factory-toolchain', 'ToolchainCenter.vue', ROOT / 'overlays/platform/ToolchainCenter.vue'),
    ]
    for view, filename, source in files:
        view_dir = target / f'frontend/web/src/views/{view}'
        view_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, view_dir / filename)

    api_dir = target / 'frontend/web/src/api/module_factory'
    api_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'overlays/platform/api/index.ts', api_dir / 'index.ts')

    menu_path = target / 'frontend/web/src/router/MenuProcessor.ts'
    text = menu_path.read_text(encoding='utf-8')
    marker = '// AI-RND-FRONTEND-ROUTE:factory:v2'
    if marker in text:
        return
    needle = 'export const builtinFrontendRoutes: AppRouteRecord[] = [];'
    if needle not in text:
        raise RuntimeError('builtinFrontendRoutes extension point changed; refusing to patch factory workbench blindly')
    routes = [
        ('/factory', 'rnd-factory', 'factory/FactoryConsole', 'AI 研发工作台', 'ri:code-box-line'),
        ('/factory-providers', 'rnd-factory-providers', 'factory-providers/ProviderManager', '模型供应商', 'ri:brain-line'),
        ('/factory-toolchain', 'rnd-factory-toolchain', 'factory-toolchain/ToolchainCenter', '研发工具链', 'ri:flow-chart'),
    ]
    lines = [marker, '// AI-RND-FASTAPIADMIN-WORKBENCH:v3', 'export const builtinFrontendRoutes: AppRouteRecord[] = [']
    for path, name, component, title, icon in routes:
        lines += [
            '  {',
            f'    path: {json.dumps(path, ensure_ascii=False)},',
            f'    name: {json.dumps(name, ensure_ascii=False)},',
            f'    component: {json.dumps(component, ensure_ascii=False)},',
            '    meta: {',
            f'      title: {json.dumps(title, ensure_ascii=False)},',
            f'      icon: {json.dumps(icon, ensure_ascii=False)},',
            '      hidden: false,',
            '      isHide: false,',
            '      keepAlive: true,',
            '    },',
            '  },',
        ]
    lines.append('];')
    menu_path.write_text(text.replace(needle, '\n'.join(lines), 1), encoding='utf-8')


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
    install_factory_frontend(destination)
    (destination / 'frontend/web/.env.production').write_text(
        'VITE_APP_ENV=prod\nVITE_APP_TITLE=AI R&D Factory\n'
        'VITE_ACCESS_MODE=mixed\n'
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

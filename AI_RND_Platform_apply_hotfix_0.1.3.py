#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def backup(path: Path) -> None:
    bak = path.with_name(path.name + '.pre-0.1.3.bak')
    if not bak.exists():
        shutil.copy2(path, bak)
        print(f'BACKUP:  {bak}')


def add_safe_flags(text: str, indent: str) -> str:
    anchor = f'{indent}DEMO_ENABLE: "False"\n'
    block = anchor + f'{indent}SCHEDULER_ALLOW_CODE_EXEC: "False"\n{indent}IP_LOCATION_ENABLE: "False"\n'
    if f'{indent}SCHEDULER_ALLOW_CODE_EXEC:' in text:
        return text
    if anchor not in text:
        raise RuntimeError(f'Could not find DEMO_ENABLE anchor with indent {indent!r}')
    return text.replace(anchor, block, 1)


def patch_platform(path: Path) -> bool:
    old = path.read_text(encoding='utf-8')
    text = old
    # Local compose is explicitly DEVELOPMENT ONLY and has no TLS terminator.
    text = text.replace('    ENVIRONMENT: prod\n', '    ENVIRONMENT: dev\n', 1)
    text = add_safe_flags(text, '    ')
    # Idempotently fix the one-shot volume initializer.
    start = text.find('  temporal-init:\n')
    if start < 0:
        raise RuntimeError('temporal-init service not found')
    end = text.find('\n  temporal:\n', start)
    if end < 0:
        raise RuntimeError('temporal service boundary not found')
    section = text[start:end]
    section = section.replace('image: temporalio/temporal:1.8.3', 'image: alpine:3.20', 1)
    text = text[:start] + section + text[end:]
    if text != old:
        backup(path)
        path.write_text(text, encoding='utf-8')
        print(f'PATCHED: {path}')
        return True
    print(f'UNCHANGED: {path}')
    return False


def patch_product(path: Path) -> bool:
    old = path.read_text(encoding='utf-8')
    text = old.replace('      ENVIRONMENT: prod\n', '      ENVIRONMENT: dev\n', 1)
    text = add_safe_flags(text, '      ')
    if text != old:
        backup(path)
        path.write_text(text, encoding='utf-8')
        print(f'PATCHED: {path}')
        return True
    print(f'UNCHANGED: {path}')
    return False


def main() -> None:
    compose = ROOT / 'compose.yaml'
    product = ROOT / 'overlays' / 'product' / 'compose.yaml'
    if not compose.exists():
        raise SystemExit(f'Run this script from the project root; missing {compose}')
    patch_platform(compose)
    if product.exists():
        patch_product(product)
    print('\nNext commands:')
    print('  docker compose config --quiet')
    print('  docker compose up -d --force-recreate api worker')
    print('  docker compose ps -a')
    print("  curl -fsS http://127.0.0.1:8000/factory-api/health")
    print("  docker compose logs --tail=100 api worker temporal")


if __name__ == '__main__':
    main()

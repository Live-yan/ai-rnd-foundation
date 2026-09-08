#!/usr/bin/env python3
"""Apply AI R&D Platform Foundation 0.1.1 clean-checkout frontend build hotfix.
Run this file from the ai-rnd-foundation project root. Stdlib only and idempotent.
"""
from pathlib import Path
import sys

ROOT = Path.cwd()
required = [ROOT / 'Dockerfile', ROOT / 'overlays/product/Dockerfile.delivery']
if not all(p.is_file() for p in required):
    raise SystemExit('ERROR: run this script from the ai-rnd-foundation project root.')

old = 'RUN pnpm exec vue-tsc --noEmit && pnpm exec vite build --base=/web/'
new = ('RUN pnpm exec vite build --mode production --base=/web/ && \\\n'
       '    test -s src/types/auto-imports.d.ts && test -s src/types/components.d.ts && \\\n'
       '    pnpm exec vue-tsc --noEmit')

changed = 0
for p in required:
    text = p.read_text(encoding='utf-8')
    if new in text:
        print(f'OK already patched: {p}')
        continue
    if old not in text:
        raise SystemExit(f'ERROR: expected 0.1.0 build marker not found in {p}; do not patch blindly.')
    p.write_text(text.replace(old, new), encoding='utf-8')
    print(f'PATCHED: {p}')
    changed += 1

p = ROOT / 'factory/generator.py'
if p.is_file():
    text = p.read_text(encoding='utf-8')
    old_doc = '再执行 `pnpm exec vue-tsc --noEmit && pnpm exec vite build --base=/web/`。'
    new_doc = '先执行 `pnpm exec vite build --mode production --base=/web/` 以生成自动导入类型声明，确认 `src/types/auto-imports.d.ts` 与 `src/types/components.d.ts` 已生成，再执行 `pnpm exec vue-tsc --noEmit`。'
    if old_doc in text:
        p.write_text(text.replace(old_doc, new_doc), encoding='utf-8')
        print(f'PATCHED: {p}')
        changed += 1

print(f'DONE: {changed} file change(s).')
print('Next: docker compose build --no-cache api && docker compose up -d')

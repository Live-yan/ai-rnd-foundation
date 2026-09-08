"""Run from product root: uv run --project backend python scripts/run_local.py."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
config = root / 'backend/env/.env.dev'
if not config.exists():
    raise SystemExit('First run: python scripts/init_product.py')
for line in config.read_text(encoding='utf-8').splitlines():
    if '=' in line and not line.startswith('#'):
        key, value = line.split('=',1); os.environ[key.strip()] = value.strip()
os.chdir(root / 'backend')
subprocess.run([sys.executable, '-m', 'alembic', '-c', 'business-alembic.ini', 'upgrade', 'head'], check=True)
subprocess.run([sys.executable, '-m', 'uvicorn', 'delivery_entry:create_app', '--factory', '--host', '127.0.0.1', '--port', '8010'], check=True)

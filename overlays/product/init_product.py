"""Initialize local development configuration; reruns keep existing secrets."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
env = root / '.env'
if not env.exists():
    env.write_text('COMPOSE_PROJECT_NAME=product-' + secrets.token_hex(3) + '\n' +
                   '\n'.join(f'{key}={secrets.token_hex(32)}' for key in
                             ['DATABASE_PASSWORD', 'REDIS_PASSWORD', 'SECRET_KEY']) + '\n', encoding='utf-8')
    env.chmod(0o600)
values = dict(line.split('=',1) for line in env.read_text().splitlines() if '=' in line and not line.startswith('#'))
local = root / 'backend/env/.env.dev'
local.parent.mkdir(parents=True, exist_ok=True)
if not local.exists():
    local.write_text('ENVIRONMENT=dev\nDATABASE_TYPE=postgres\nDATABASE_HOST=127.0.0.1\nDATABASE_PORT=55433\n'
                     'DATABASE_USER=product\nDATABASE_NAME=product\nREDIS_HOST=127.0.0.1\nREDIS_PORT=56380\n'
                     'SERVER_HOST=127.0.0.1\nSERVER_PORT=8010\nDEBUG=False\nDEMO_ENABLE=False\n' +
                     '\n'.join(f'{k}={values[k]}' for k in ['DATABASE_PASSWORD','REDIS_PASSWORD','SECRET_KEY']) + '\n', encoding='utf-8')
    local.chmod(0o600)
frontend = root / 'frontend/web/.env.production'
if not frontend.exists():
    frontend.write_text((root / 'frontend/web/.env.production.example').read_text())
print('Initialized. Docker: docker compose up --build -d. Open http://localhost:8010/api/v1/web/#/business after login.')

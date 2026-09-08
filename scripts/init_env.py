"""Generate local development secrets once. Never overwrites an existing .env."""
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / '.env'
    if target.exists():
        print('.env already exists; kept unchanged.')
        return
    password = secrets.token_hex(24)
    values = {
        'COMPOSE_PROJECT_NAME': 'ai-rnd',
        'POSTGRES_PASSWORD': password,
        'REDIS_PASSWORD': secrets.token_hex(24),
        'SECRET_KEY': secrets.token_hex(48),
        'FACTORY_TOKEN': secrets.token_hex(32),
        'FACTORY_DATABASE_URL': f'postgresql+psycopg://factory:{password}@postgres:5432/factory',
        'FACTORY_MODEL_API_KEY': '',
        'FACTORY_MODEL_NAME': 'factory-planner',
        'FACTORY_MODEL_BASE_URL': 'http://litellm:4000/v1',
        'LITELLM_MASTER_KEY': 'sk-' + secrets.token_hex(24),
        'OLLAMA_MODEL': 'REPLACE_WITH_AN_INSTALLED_MODEL',
        'FACTORY_SERENA_URL': '',
        'FACTORY_SERENA_TOKEN': '',
        'FACTORY_CUBE_API_URL': '',
        'FACTORY_CUBE_API_KEY': '',
        'FACTORY_CUBE_TEMPLATE': '',
        'FACTORY_CODER_URL': '',
        'FACTORY_CODER_TOKEN': '',
        'FACTORY_CODER_TEMPLATE_ID': '',
        'FACTORY_CODER_OWNER_ID': '',
        'FACTORY_DOCKER_HOST_DATA_DIR': str(ROOT / 'data'),
    }
    target.write_text('# Local-only. Do not upload this file.\n' +
                      '\n'.join(f'{k}={v}' for k, v in values.items()) + '\n', encoding='utf-8')
    target.chmod(0o600)
    (ROOT / 'data').mkdir(exist_ok=True)
    print('Created .env with random secrets. Demo does not require a model key.')


if __name__ == '__main__':
    main()

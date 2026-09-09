"""Connect the planner to an already installed Ollama model; stdlib only."""
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
path = root / '.env'
if not path.exists():
    raise SystemExit('First run scripts/init_env.py')
text = path.read_text()
values = dict(line.split('=',1) for line in text.splitlines() if '=' in line and not line.startswith('#'))
model = values.get('OLLAMA_MODEL','')
if not model or model == 'REPLACE_WITH_AN_INSTALLED_MODEL':
    raise SystemExit('Run ollama list, then put an exact installed model name into OLLAMA_MODEL in .env')
key = values['LITELLM_MASTER_KEY']
lines = text.splitlines()
lines = [f'FACTORY_MODEL_API_KEY={key}' if line.startswith('FACTORY_MODEL_API_KEY=') else line for line in lines]
path.write_text('\n'.join(lines) + '\n')
# JSON is valid YAML. Dumping data avoids YAML injection from a model name.
config = {'model_list':[{'model_name':'factory-planner','litellm_params':{
    'model':'ollama_chat/' + model,'api_base':'http://host.docker.internal:11434','timeout':90,'max_tokens':6000}}],
    'general_settings':{'master_key':'os.environ/LITELLM_MASTER_KEY'},'litellm_settings':{'drop_params':False}}
(root / 'integrations/litellm/config.yaml').write_text(json.dumps(config,indent=2))
print('Configured Ollama through LiteLLM. Start: docker compose --profile ai up -d --force-recreate api worker litellm')

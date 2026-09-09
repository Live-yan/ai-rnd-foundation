"""Real opt-in integration probes. Never interpret configured as healthy."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run(target):
    from factory.config import Settings
    s = Settings()
    if target == 'serena':
        from factory.providers.mcp import SerenaClient
        text = await SerenaClient(s).template_context()
        print(json.dumps({'target': target, 'read_probe': 'passed', 'characters': len(text)}))
    elif target == 'coder':
        import httpx
        if not s.coder_url or not s.coder_token:
            raise ValueError('Configure Coder URL/token first')
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(s.coder_url.rstrip('/') + '/api/v2/users/me', headers={'Coder-Session-Token': s.coder_token})
            r.raise_for_status()
            print(json.dumps({'target': target, 'identity_read': 'passed', 'workspace_created': False}))
    elif target == 'cube':
        if not all([s.cube_api_url, s.cube_api_key, s.cube_template]):
            raise ValueError('Configure Cube endpoint/key/template first')
        from e2b_code_interpreter import Sandbox
        with Sandbox.create(template=s.cube_template, api_key=s.cube_api_key, api_url=s.cube_api_url,
                            timeout=90, allow_internet_access=False) as box:
            result = box.commands.run("python -c 'import sys; print(sys.version)'", timeout=30)
            if result.exit_code != 0:
                raise RuntimeError('Cube fixed-command probe failed')
        print(json.dumps({'target': target, 'temporary_sandbox_fixed_command': 'passed', 'full_stack': 'not_run'}))
    elif target == 'temporal':
        from temporalio.client import Client
        await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
        print(json.dumps({'target': target, 'connected': True, 'worker_execution': 'not_verified'}))
    elif target == 'model':
        from factory.providers.llm import LiteLLMPlanner
        from factory.schemas import ProjectSpec
        result = await LiteLLMPlanner(s).draft('Create a device register with a name and enabled flag. Only basic CRUD.', '')
        spec = ProjectSpec.model_validate(result)
        print(json.dumps({'target': target, 'structured_spec': 'passed', 'entities': len(spec.entities)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('target', choices=['serena', 'coder', 'cube', 'temporal', 'model'])
    try:
        asyncio.run(run(p.parse_args().target))
    except Exception as e:
        # Do not dump HTTP bodies or environment variables: they can contain secrets.
        print(f'Probe failed ({type(e).__name__}); check private service logs and configuration.', file=sys.stderr)
        raise SystemExit(1)

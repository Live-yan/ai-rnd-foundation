from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from .config import Settings
from .providers.sandbox import cube_verify, docker_verify


def execute_json(args: list[str], cwd: Path, timeout: int = 90) -> dict:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout,
                            env={'PATH':os.environ.get('PATH',''), 'PYTHONDONTWRITEBYTECODE':'1', 'LANG':'C.UTF-8'})
    if result.returncode:
        raise RuntimeError('Verification failed: ' + result.stderr[-2000:] + result.stdout[-1000:])
    return json.loads(result.stdout)


def verify_product(product: Path, run_id: str, request: dict, settings: Settings) -> dict:
    report = {'quality_level':'scaffold_ready', 'full_stack':'not_run', 'production_ready':False,
              'frontend_build':'not_run', 'postgres_integration':'not_run', 'upstream_auth':'not_run',
              'requested_provider':request['provider'], 'requested_sandbox':request['sandbox']}
    report['source'] = execute_json([sys.executable, str(product / 'scripts/verify_source.py')], product)
    report['business_contract'] = execute_json([sys.executable, str(product / 'scripts/verify_business.py')], product)
    openspec = shutil.which('openspec')
    if not openspec:
        if settings.openspec_required:
            raise RuntimeError('OpenSpec CLI missing. Install @fission-ai/openspec@1.12.0')
        report['openspec'] = 'not_run_cli_missing'
    else:
        result = subprocess.run([openspec, 'validate', 'create-product', '--type', 'change', '--strict', '--no-interactive'],
                                cwd=product, text=True, capture_output=True, timeout=45,
                                env={'PATH':os.environ.get('PATH',''), 'HOME':'/tmp', 'LANG':'C.UTF-8', 'OPENSPEC_TELEMETRY':'0', 'CI':'1'})
        report['openspec'] = {'exit_code':result.returncode, 'output':(result.stdout + result.stderr)[-5000:]}
        if result.returncode:
            raise RuntimeError('OpenSpec validation did not pass: ' + report['openspec']['output'][-2000:])
    if request['sandbox'] == 'docker':
        report['sandbox'] = docker_verify(product, run_id, settings)
    elif request['sandbox'] == 'cube':
        report['sandbox'] = cube_verify(product, settings)
    else:
        report['sandbox'] = {'provider':'static', 'scope':'trusted_source_and_business_contracts_only',
                             'untrusted_code_execution':'disabled'}
    report['architecture'] = json.loads((product / 'delivery/receipt.json').read_text())['architecture']
    return report

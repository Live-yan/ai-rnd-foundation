"""Isolated source checks and fail-closed Cube product acceptance; never fall back to host execution."""
from __future__ import annotations
import io
import hashlib
import json
import subprocess
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile, ZIP_DEFLATED
from ..config import Settings
from ..packaging import files_for_package


def docker_verify(product: Path, run_id: str, settings: Settings) -> dict:
    run_id = str(UUID(run_id))
    if not settings.docker_host_data_dir:
        raise ValueError('Docker host-side data path is required')
    host_path = Path(settings.docker_host_data_dir) / 'runs' / run_id / 'product'
    if ',' in str(host_path):
        raise ValueError('Docker bind mount path must not contain commas')
    name = 'rnd-verify-' + run_id
    args = ['docker', 'run', '--rm', '--name', name, '--network', 'none', '--read-only',
            '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=128',
            '--memory=512m', '--cpus=1', '--user=65534:65534',
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
            '--mount', f'type=bind,source={host_path},target=/workspace,readonly',
            settings.verifier_image, 'python', '/workspace/scripts/verify_source.py']
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError('Docker source verification failed: ' + result.stderr[-1500:])
        return {'provider':'docker', 'result':json.loads(result.stdout), 'scope':'source_only'}
    finally:
        # Covers a killed CLI or a failed verification; an orphaned container must not run forever.
        try:
            subprocess.run(['docker','rm','-f',name], capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            pass  # An administrator should inspect daemon state after a connectivity failure.


def cube_verify(product: Path, settings: Settings, *, full_stack: bool = False) -> dict:
    from e2b_code_interpreter import Sandbox
    if not all([settings.cube_api_url, settings.cube_api_key, settings.cube_template]):
        raise ValueError('Cube API URL, API key and template ID are required')
    data = io.BytesIO()
    with ZipFile(data, 'w', compression=ZIP_DEFLATED) as archive:
        for path in files_for_package(product):
            archive.write(path, path.relative_to(product).as_posix())
    payload = data.getvalue()
    if len(payload) > 128 * 1024 * 1024:
        raise ValueError('Cube verification upload exceeds 128 MiB')
    with Sandbox.create(template=settings.cube_template, api_url=settings.cube_api_url,
                        api_key=settings.cube_api_key, timeout=720 if full_stack else 180,
                        allow_internet_access=False) as sandbox:
        sandbox.files.write('/tmp/rnd-input.zip', payload)
        if full_stack:
            digest = hashlib.sha256(payload).hexdigest()
            # The verifier is baked into the trusted template, not accepted from uploaded code.
            command = ("/opt/rnd-runtime/.venv/bin/python /opt/rnd-verifier/full_stack.py "
                       "--archive /tmp/rnd-input.zip --sha256 " + digest + " --report /tmp/rnd-full-report.json")
            result = sandbox.commands.run(command, timeout=660, user="factory")
            if result.exit_code:
                raise RuntimeError("Cube full-stack acceptance failed; source-only checks cannot complete full mode")
            receipt = sandbox.files.read('/tmp/rnd-full-report.json')
            if len(receipt) > 64000:
                raise RuntimeError("Cube acceptance receipt exceeds the size limit")
            report = json.loads(receipt)
            if report.get('archive_sha256') != digest or report.get('full_stack') != 'passed':
                raise RuntimeError("Cube acceptance receipt is missing or does not match the uploaded source")
            return {'provider': 'cube', 'result': report, 'scope': 'generated_crud_stack',
                    'input_sha256': digest, 'sandbox_id': sandbox.sandbox_id,
                    'lifecycle': 'context_manager_teardown'}
        # Fixed command over a self-produced ZIP; no user/model text interpolated into shell.
        command = ('mkdir -p /tmp/rnd-product && '
                   'python3 -m zipfile -e /tmp/rnd-input.zip /tmp/rnd-product && '
                   'python3 /tmp/rnd-product/scripts/verify_source.py')
        result = sandbox.commands.run(command, timeout=90)
        if result.exit_code:
            raise RuntimeError('Cube source verification failed: ' + str(result.stderr)[-1500:])
        return {'provider':'cube', 'result':json.loads(result.stdout), 'scope':'source_only',
                'sandbox_id':sandbox.sandbox_id, 'lifecycle':'context_manager_teardown'}

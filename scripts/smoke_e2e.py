"""Opt-in real API -> Temporal -> approval -> ZIP smoke test. Requires an existing real login token."""
import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
import httpx


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', default='http://127.0.0.1:8000')
    p.add_argument('--accept-demo', action='store_true', help='Explicitly approve fixed-demo limitations')
    p.add_argument('--timeout', type=int, default=900)
    p.add_argument('--output', type=Path, default=Path('reports/live-smoke'))
    args = p.parse_args()
    token = os.environ.get('FACTORY_LOGIN_TOKEN')
    if not token or not args.accept_demo:
        raise SystemExit('Set FACTORY_LOGIN_TOKEN to your own current FastapiAdmin bearer token and add --accept-demo')
    args.output.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=args.base_url.rstrip('/')+'/factory-api/',
                      headers={'Authorization': 'Bearer '+token}, timeout=45) as c:
        def request(method, path, **kw):
            r = c.request(method, path, **kw)
            if r.status_code >= 400:
                raise RuntimeError(f'{method} {path} returned HTTP {r.status_code}; inspect service logs privately')
            return r
        project = request('POST', 'projects', json={'title':'Local acceptance demo',
                          'requirement':'Create the fixed demo device register and maintenance records.'}).json()
        run = request('POST', f"projects/{project['id']}/runs", json={'provider':'demo', 'sandbox':'static',
                      'idempotency_key':str(uuid.uuid4())}).json()
        run_id = run['id']; start = time.monotonic(); approved = False
        while time.monotonic()-start < args.timeout:
            run = request('GET', f'runs/{run_id}').json()
            print(run['status'], flush=True)
            if run['status'] == 'AWAITING_APPROVAL' and not approved:
                request('POST', f'runs/{run_id}/decision', json={'approve':True,'spec_digest':run['spec_digest'],
                         'accept_limitations':True})
                approved = True
            elif run['status'] == 'READY':
                download = request('GET', f'runs/{run_id}/download')
                sha = hashlib.sha256(download.content).hexdigest()
                if sha != download.headers.get('x-content-sha256'):
                    raise RuntimeError('Downloaded archive hash mismatch')
                (args.output/'product.zip').write_bytes(download.content)
                (args.output/'result.json').write_text(json.dumps({'run_id':run_id,'sha256':sha,
                    'control_flow':'passed', 'quality':run.get('checks'),
                    'fresh_product_compose':'not_run_by_this_script', 'model':'fixed_demo_not_real_ai'},
                    ensure_ascii=False, indent=2), encoding='utf-8')
                print('Control flow passed. Fresh product deployment is a separate mandatory acceptance step.')
                return
            elif run['status'] in ('FAILED','REJECTED','CANCELLED','TIMED_OUT'):
                raise RuntimeError(f'Run stopped in state {run["status"]}; read authenticated events')
            time.sleep(3)
        raise TimeoutError('No terminal state before timeout; check outbox dispatcher, worker, and Temporal')


if __name__ == '__main__':
    main()

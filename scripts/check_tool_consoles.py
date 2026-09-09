"""CI-only bounded HTTP readiness checks, no account or model calls."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request


def wait_for(name: str, url: str) -> None:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=4) as response:
                if response.status == 200:
                    print(name + ': HTTP readiness passed (no account configured)')
                    return
        except (OSError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError(name + ': console readiness timed out')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace-network', help='Also test Coder from the built workspace image on this private network')
    args = parser.parse_args()
    out = Path('tool-console-reports')
    out.mkdir(exist_ok=True)
    receipt = {'account_configuration': 'not_run'}
    try:
        for name, url in {
            'coder': 'http://127.0.0.1:7080/api/v2/buildinfo',
            'litellm': 'http://127.0.0.1:4000/health/liveliness',
        }.items():
            wait_for(name, url)
            receipt[name] = 'reachable'
        if args.workspace_network:
            # Fixed unauthenticated request from the actual workspace image;
            # never pass a host socket, API token or platform environment.
            subprocess.run([
                'docker', 'run', '--rm', '--network', args.workspace_network,
                '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                '--entrypoint', 'python3', 'ai-rnd-coder:0.2.0', '-c',
                "import json,urllib.request; r=urllib.request.urlopen('http://coder:7080/api/v2/buildinfo',timeout=10); assert r.status==200; assert json.load(r).get('version')",
            ], check=True, timeout=30, capture_output=True)
            receipt['coder_workspace_network'] = 'reachable'
    except Exception as error:
        # Reports must also exist on failure; do not dump subprocess output or
        # full Compose config which may contain credentials.
        receipt['failure'] = type(error).__name__
        raise
    finally:
        (out / 'readiness.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()

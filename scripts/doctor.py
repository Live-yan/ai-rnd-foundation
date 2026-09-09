"""Read-only, stdlib prerequisite check; not an end-to-end health certificate."""
import json
import shutil
import subprocess
import sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]
result = {'python': sys.version.split()[0], 'root': str(R), 'env_exists': (R/'.env').is_file(),
          'upstream_downloaded_on_host': (R/'.vendor/FastapiAdmin/LICENSE').is_file(), 'checks': {}}
for command in ('docker', 'git', 'uv'):
    path = shutil.which(command)
    result['checks'][command] = 'found' if path else 'missing'
if shutil.which('docker'):
    for key, args in [('docker_daemon', ['docker','info','--format','{{.ServerVersion}}']),
                      ('compose', ['docker','compose','version'])]:
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=15)
            result['checks'][key] = p.stdout.strip()[:150] if p.returncode == 0 else 'unavailable'
        except subprocess.TimeoutExpired:
            result['checks'][key] = 'timeout'
print(json.dumps(result, ensure_ascii=False, indent=2))

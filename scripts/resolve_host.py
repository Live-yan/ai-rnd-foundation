"""Build one combined uv project without silently relaxing upstream constraints."""
import json
import tomllib
import hashlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
upstream = tomllib.loads((root / 'runtime/FastapiAdmin/backend/pyproject.toml').read_text())
ours = tomllib.loads((root / 'pyproject.toml').read_text())
dependencies = sorted(set(upstream['project']['dependencies'] + ours['project']['dependencies'] +
                          ours['project']['optional-dependencies']['cube']))
output = root / 'runtime/combined'
output.mkdir(parents=True,exist_ok=True)
text = '[project]\nname="ai-rnd-host"\nversion="0.2.0"\nrequires-python=">=3.12,<3.13"\ndependencies=[\n'
text += ''.join('  ' + json.dumps(d) + ',\n' for d in dependencies) + ']\n'
(output / 'pyproject.toml').write_text(text)
print('Combined dependency manifest SHA-256:', hashlib.sha256(text.encode()).hexdigest())
print(text)
print('Run uv lock --directory runtime/combined, then uv sync --directory runtime/combined --frozen.')

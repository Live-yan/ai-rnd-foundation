#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
command -v git >/dev/null; command -v docker >/dev/null
python3 scripts/bootstrap.py --fetch-only
mkdir -p locks runtime/serena-home
if [ ! -s locks/serena.ref ]; then
  git ls-remote https://github.com/oraios/serena.git HEAD | cut -f1 > locks/serena.ref
fi
REF=$(cat locks/serena.ref)
[[ "$REF" =~ ^[a-f0-9]{40}$ ]] || { echo "Invalid Serena commit" >&2; exit 1; }
# This is a dedicated template copy, never platform data, user projects, or the host home.
python3 - <<'EOF'
from pathlib import Path
from scripts.bootstrap import copy_source
src=Path('.vendor/FastapiAdmin'); dst=Path('runtime/serena-template')
if not (dst/'backend').exists(): copy_source(src,dst)
EOF
docker build --build-arg SERENA_REF="$REF" -f integrations/toolhive/Dockerfile.serena -t ai-rnd-serena:locked .
# Initialization may install language servers. Network is permitted only in this trusted preparation phase.
docker run --rm -v "$PWD/runtime/serena-template:/template" \
  -v "$PWD/runtime/serena-home:/root/.serena" ai-rnd-serena:locked project create --index
printf '\nPrepared a dedicated template copy. Read README.md before exposing the MCP endpoint.\n'

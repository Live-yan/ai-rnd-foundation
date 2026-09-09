#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
command -v thv >/dev/null
[ -f runtime/serena-template/.serena/project.yml ] || { echo "Run prepare.sh and verify project initialization first" >&2; exit 1; }
# Root is read-only; Serena may update only its own template index/cache and service configuration.
# ToolHive proxy remains loopback-only. Container-to-host connectivity must be checked separately.
thv run --name factory-serena --transport streamable-http \
  --host 127.0.0.1 --proxy-port 9122 --target-port 9121 \
  --tools get_symbols_overview,find_symbol,search_for_pattern,list_dir \
  --volume "$PWD/runtime/serena-template:/template:ro" \
  --volume "$PWD/runtime/serena-template/.serena:/template/.serena" \
  --volume "$PWD/runtime/serena-home:/root/.serena" \
  ai-rnd-serena:locked

#!/usr/bin/env bash
# CI only: the same approved ZIP is exercised in the actual Cube base image.
# This verifies the image, NOT a live Cube cluster's envd/network/authorization.
set -euo pipefail
: "${RUNNER_TEMP:?This check is for disposable GitHub Actions runners}"
stage="$(mktemp -d "$RUNNER_TEMP/rnd-cube-image.XXXXXX")"
name="rnd-cube-image-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
trap 'docker rm -f "$name" >/dev/null 2>&1 || true; rm -rf "$stage"' EXIT
archive="$(sudo find data/runs -name product.zip -type f -print -quit)"
test -n "$archive"
sudo install -m 0644 "$archive" "$stage/product.zip"
sudo install -m 0644 data/ci-reports/platform-run.json "$stage/platform-run.json"
sudo chown "$(id -u):$(id -g)" "$stage/product.zip" "$stage/platform-run.json"
chmod 755 "$stage"
digest="$(python3 - "$stage" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
expected = json.loads((root / 'platform-run.json').read_text())['artifact_sha256']
assert hashlib.sha256((root / 'product.zip').read_bytes()).hexdigest() == expected
print(expected)
PY
)"
docker create --name "$name" --user 10001:10001 --network none \
  --cap-drop=ALL --security-opt=no-new-privileges --memory=6g --cpus=2 --pids-limit=512 \
  --mount "type=bind,source=$stage/product.zip,target=/tmp/rnd-input.zip,readonly" \
  --entrypoint /opt/rnd-runtime/.venv/bin/python ai-rnd-cube-verifier:ci \
  /opt/rnd-verifier/full_stack.py --archive /tmp/rnd-input.zip \
  --sha256 "$digest" --report /tmp/rnd-image-receipt.json >/dev/null
timeout 720 docker start --attach "$name"
test "$(docker inspect --format '{{.State.ExitCode}}' "$name")" = 0
docker cp "$name:/tmp/rnd-image-receipt.json" "$stage/receipt.json"
python3 - "$stage/receipt.json" "$digest" <<'PY'
import json, sys
from pathlib import Path
value = json.loads(Path(sys.argv[1]).read_text())
assert value['archive_sha256'] == sys.argv[2]
for key in ('full_stack', 'frontend_build', 'frontend_types', 'upstream_auth', 'redis_sessions', 'business_owner_isolation'):
    assert value.get(key) == 'passed', key
value['execution_environment'] = 'actual_cube_image_in_offline_CI_container'
value['live_cube_cluster'] = 'not_run'
Path(sys.argv[1]).write_text(json.dumps(value, indent=2))
PY
sudo install -m 0644 "$stage/receipt.json" data/ci-reports/cube-image-stack.json
printf 'Actual Cube image: offline generated-product acceptance passed\n'

"""CI-only bounded HTTP readiness checks, no account or model calls."""
import json
from pathlib import Path
import time
import urllib.request

if __name__ == "__main__":
    endpoints = {"coder": "http://127.0.0.1:7080/api/v2/buildinfo",
                 "litellm": "http://127.0.0.1:4000/health/liveliness"}
    for name, url in endpoints.items():
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=4) as response:
                    if response.status == 200:
                        print(name + ": HTTP readiness passed (no account configured)")
                        break
            except Exception:
                pass
            time.sleep(2)
        else:
            raise SystemExit(name + ": console readiness timed out")
    out = Path("tool-console-reports")
    out.mkdir(exist_ok=True)
    (out / "readiness.json").write_text(json.dumps({"coder": "reachable", "litellm": "reachable", "account_configuration": "not_run"}))

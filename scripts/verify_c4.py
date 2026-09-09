"""Run the pinned Structurizr parser against real generator fixtures, not mocks."""
from pathlib import Path
import hashlib
import json
import subprocess

from factory.artifacts import c4_dsl
from factory.schemas import demo_spec


def main():
    directory = Path("c4-reports").resolve()
    directory.mkdir(exist_ok=True)
    cases = {"english": "Device maintenance", "chinese": "设备检修管理示例",
             "special": '设备 "quoted" ${SECRET}\n!include /etc/passwd\ufeff'}
    results = []
    for key, title in cases.items():
        spec = demo_spec()
        spec.title = title
        if key == "special":
            for entity in spec.entities:
                entity.label = "Authentication adapter"
        path = directory / (key + ".dsl")
        path.write_text(c4_dsl(spec), encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop=ALL",
                   "--security-opt=no-new-privileges", "--memory=1g", "--pids-limit=256",
                   "--tmpfs", "/tmp:rw,nosuid,size=128m", "--mount",
                   f"type=bind,source={directory},target=/usr/local/structurizr,readonly",
                   "--entrypoint", "java", "structurizr/structurizr:2026.06.28-noble",
                   "-Dfile.encoding=UTF-8", "-jar", "/usr/local/structurizr.war", "validate", "-w",
                   "/usr/local/structurizr/" + path.name]
        completed = subprocess.run(command, text=True, capture_output=True, timeout=120)
        (directory / (key + ".log")).write_text(completed.stdout + completed.stderr)
        print(key, digest, "exit", completed.returncode, flush=True)
        print(completed.stdout + completed.stderr, flush=True)
        results.append({"case": key, "sha256": digest, "exit_code": completed.returncode})
    (directory / "parser.json").write_text(json.dumps(results, indent=2))
    if any(result["exit_code"] != 0 for result in results):
        raise SystemExit("Generated C4 DSL did not pass the real parser")


if __name__ == "__main__":
    main()

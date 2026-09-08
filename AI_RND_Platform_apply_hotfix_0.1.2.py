#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path.cwd()
COMPOSE = ROOT / "compose.yaml"

if not COMPOSE.exists():
    raise SystemExit("compose.yaml not found. Run this script from the ai-rnd-foundation project root.")

text = COMPOSE.read_text(encoding="utf-8")
if "  temporal-init:\n" in text:
    print("SKIP: temporal-init already present; compose.yaml is already patched.")
    print("Next: docker compose up -d")
    raise SystemExit(0)

old = '''  temporal:\n    image: temporalio/temporal:1.8.3\n    command: ["server", "start-dev", "--ip", "0.0.0.0", "--db-filename", "/data/temporal.db", "--ui-port", "8233"]\n    ports: ["127.0.0.1:7233:7233", "127.0.0.1:8233:8233"]\n    volumes: ["temporal-data:/data"]\n    healthcheck:\n      test: ["CMD", "temporal", "operator", "cluster", "health", "--address", "127.0.0.1:7233"]\n      interval: 5s\n      timeout: 5s\n      retries: 30\n    restart: unless-stopped\n'''

new = '''  # Temporal runs as uid/gid 1000. Initialize the named volume before SQLite opens it.\n  temporal-init:\n    image: temporalio/temporal:1.8.3\n    user: "0:0"\n    command: ["sh", "-c", "mkdir -p /data && chown -R 1000:1000 /data && chmod 700 /data"]\n    volumes: ["temporal-data:/data"]\n    restart: "no"\n  temporal:\n    image: temporalio/temporal:1.8.3\n    command: ["server", "start-dev", "--ip", "0.0.0.0", "--db-filename", "/data/temporal.db", "--ui-port", "8233"]\n    ports: ["127.0.0.1:7233:7233", "127.0.0.1:8233:8233"]\n    volumes: ["temporal-data:/data"]\n    depends_on:\n      temporal-init: {condition: service_completed_successfully}\n    healthcheck:\n      test: ["CMD", "temporal", "operator", "cluster", "health", "--address", "127.0.0.1:7233"]\n      interval: 5s\n      timeout: 5s\n      retries: 30\n    restart: unless-stopped\n'''

if old not in text:
    raise SystemExit("Expected Temporal block was not found; refusing to edit an unknown compose.yaml.")

backup = COMPOSE.with_suffix(".yaml.pre-0.1.2.bak")
if not backup.exists():
    shutil.copy2(COMPOSE, backup)

COMPOSE.write_text(text.replace(old, new, 1), encoding="utf-8")
print(f"PATCHED: {COMPOSE}")
print(f"BACKUP:  {backup}")
print("Next commands:")
print("  docker compose config --quiet")
print("  docker compose up -d")
print("  docker compose ps -a")
print("  docker compose logs --tail=120 temporal worker api")

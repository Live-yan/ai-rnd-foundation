"""Fixed offline acceptance runner for a disposable Cube VM or CI container.

Run as a non-root user. All services/data/credentials are created in a private
TemporaryDirectory, never using an operator's PostgreSQL or Redis. Dependencies
must be baked into the verifier image; this command cannot install packages.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_check(args: list[str], *, cwd: Path, env: dict, phase: str, timeout: int = 180) -> None:
    # Never serialize subprocess exception chains (they can contain credentials).
    try:
        result = subprocess.run(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError(f"Acceptance phase {phase} could not complete") from None
    if result.returncode:
        raise RuntimeError(f"Acceptance phase {phase} failed (exit {result.returncode})")


def verify(archive: Path, sha256: str) -> dict:
    if os.geteuid() == 0:
        raise RuntimeError("Acceptance must run as the unprivileged factory user")
    from import_source import extract_verified

    candidates = sorted(Path("/usr/lib/postgresql").glob("*/bin/pg_ctl"))
    if not candidates or not shutil.which("redis-server") or not shutil.which("pnpm"):
        raise RuntimeError("Use the fullstack verifier image with PostgreSQL, Redis, Node and pnpm")
    pg_bin = candidates[-1].parent
    dependency_root = Path("/opt/rnd-node")
    if not (dependency_root / "node_modules").is_dir():
        raise RuntimeError("Offline frontend dependencies are missing")
    with tempfile.TemporaryDirectory(prefix="rnd-fullstack-") as directory:
        scratch = Path(directory)
        product = scratch / "product"
        extract_verified(archive, product, sha256)
        frontend = product / "frontend/web"
        lockfile = frontend / "pnpm-lock.yaml"
        cached_lock = dependency_root / "pnpm-lock.yaml"
        if not lockfile.is_file() or not cached_lock.is_file() or lockfile.read_bytes() != cached_lock.read_bytes():
            raise RuntimeError("Verifier dependency cache does not match the delivered frontend lockfile")
        # Allowlisted process environment: NO platform JWT, API key, DB URL or SDK env.
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(scratch), "LANG": "C.UTF-8",
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1", "CI": "1",
               "NODE_OPTIONS": "--max-old-space-size=4096", "OPENSPEC_TELEMETRY": "0"}
        pg_port, redis_port = free_port(), free_port()
        while redis_port == pg_port:
            redis_port = free_port()
        database = "rnd_acceptance_" + secrets.token_hex(8)
        db_password, redis_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        pg_data = scratch / "postgres"
        run_check([str(pg_bin / "initdb"), "-D", str(pg_data), "--username=factory", "--auth=trust",
                   "--encoding=UTF8", "--no-locale"], cwd=scratch, env=env, phase="initdb")
        redis_conf = scratch / "redis.conf"
        redis_conf.write_text(f"bind 127.0.0.1\nport {redis_port}\nrequirepass {redis_password}\nsave \"\"\nappendonly no\ndir {scratch}\n")
        redis_conf.chmod(0o600)
        redis = None
        started_pg = False
        try:
            run_check([str(pg_bin / "pg_ctl"), "-D", str(pg_data), "-l", str(scratch / "postgres.log"),
                       "-o", f"-h 127.0.0.1 -p {pg_port} -k {scratch}", "-w", "start"],
                      cwd=scratch, env=env, phase="postgres-start")
            started_pg = True
            run_check([str(pg_bin / "createdb"), "-h", "127.0.0.1", "-p", str(pg_port), "-U", "factory", database],
                      cwd=scratch, env=env, phase="createdb")
            redis = subprocess.Popen(["redis-server", str(redis_conf)], cwd=scratch, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            import redis as redis_module
            connection = redis_module.Redis(host="127.0.0.1", port=redis_port, password=redis_password,
                                            socket_connect_timeout=1, socket_timeout=1)
            try:
                for _ in range(60):
                    try:
                        if connection.ping():
                            break
                    except redis_module.RedisError:
                        pass
                    if redis.poll() is not None:
                        raise RuntimeError("Disposable Redis failed to start")
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Disposable Redis readiness timed out")
            finally:
                connection.close()
            (frontend / "node_modules").symlink_to(dependency_root / "node_modules", target_is_directory=True)
            (frontend / ".env.production").write_text(
                "VITE_APP_TITLE=Acceptance Product\nVITE_APP_ENV=prod\nVITE_ACCESS_MODE=mixed\n"
                "VITE_BASE_URL=/api/v1/web/\nVITE_APP_BASE_API=/api/v1\nVITE_API_URL=/\n")
            run_check(["pnpm", "exec", "vite", "build", "--mode", "production"], cwd=frontend, env=env, phase="frontend-build")
            run_check(["pnpm", "exec", "vue-tsc", "--noEmit"], cwd=frontend, env=env, phase="frontend-types")
            shutil.copytree(frontend / "dist", product / "backend/dist", dirs_exist_ok=True)
            env.update(FACTORY_ACCEPTANCE_DISPOSABLE="1", DATABASE_TYPE="postgres", DATABASE_HOST="127.0.0.1",
                       DATABASE_PORT=str(pg_port), DATABASE_USER="factory", DATABASE_PASSWORD=db_password,
                       DATABASE_NAME=database, REDIS_HOST="127.0.0.1", REDIS_PORT=str(redis_port),
                       REDIS_PASSWORD=redis_password, SECRET_KEY=secrets.token_hex(48))
            result_path = scratch / "stack.json"
            run_check([sys.executable, str(Path(__file__).with_name("verify_delivery_stack.py")), str(product),
                       "--report", str(result_path)], cwd=scratch, env=env, phase="authenticated-product-stack")
            result = json.loads(result_path.read_text())
            required = ["postgres_integration", "upstream_auth", "redis_sessions", "business_owner_isolation", "frontend_mount"]
            if any(result.get(key) != "passed" for key in required) or result.get("assertions", 0) < 5:
                raise RuntimeError("Product acceptance did not return all required assertions")
            return {**result, "schema_version": 1, "full_stack": "passed", "frontend_build": "passed",
                    "frontend_types": "passed", "archive_sha256": sha256, "network": "offline_dependencies",
                    "scope": "generated_crud_stack", "production_ready": False}
        finally:
            if redis is not None:
                redis.terminate()
                try:
                    redis.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    redis.kill(); redis.wait(timeout=10)
            if started_pg:
                run_check([str(pg_bin / "pg_ctl"), "-D", str(pg_data), "-m", "immediate", "-w", "stop"],
                          cwd=scratch, env=env, phase="postgres-cleanup", timeout=20)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.archive.resolve(), args.sha256)
    except Exception as exc:
        # Our phase errors contain no process output/args. Other errors are intentionally opaque.
        message = str(exc) if type(exc) is RuntimeError else "Verifier failed; no success receipt was produced"
        raise SystemExit(message) from None
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("Offline generated-product acceptance passed")

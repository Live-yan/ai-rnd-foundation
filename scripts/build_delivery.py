"""Package same-commit CI evidence only after all five acceptance jobs succeed.

This is an offline release assembler, not an application endpoint. It neither
reads .env nor creates accounts, workspaces or sandboxes. CI supplies artifacts
from its own workflow run via actions/download-artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import xml.etree.ElementTree as ET
import zipfile


class DeliveryError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DeliveryError(message)


def load(root: Path, name: str):
    return json.loads((root / name).read_text(encoding="utf-8"))


def validate(root: Path, commit: str) -> dict:
    require(bool(re.fullmatch(r"[a-f0-9]{40}", commit)), "Invalid tested commit")
    require((root / "contract-results/source-commit.txt").read_text().strip() == commit,
            "Contract evidence belongs to a different commit")
    junit = ET.parse(root / "contract-results/junit-ci.xml").getroot()
    suites = list(junit.iter("testsuite"))
    cases = list(junit.iter("testcase"))
    require(bool(cases) and bool(suites), "JUnit is empty")
    for suite in suites:
        require(all(int(suite.attrib.get(key, "0")) == 0 for key in ("failures", "errors", "skipped")),
                "JUnit includes a failure, error or skipped test")
    require(not any(list(junit.iter(key)) for key in ("failure", "error", "skipped")), "JUnit case failed")
    pg = sum("test_tool_settings" in case.get("classname", "") and "postgres" in case.get("name", "") for case in cases)
    require(pg > 0, "Real PostgreSQL configuration tests are missing")
    layout = load(root, "embedded-layout-reports/layout.json")
    expected = {(route, width, height) for route in ("/factory", "/factory-providers", "/factory-toolchain")
                for width, height in ((1366, 768), (1280, 720), (820, 760), (390, 780))}
    receipts = layout.get("receipts", [])
    require({(r["route"], r["width"], r["height"]) for r in receipts} == expected,
            "Actual-page viewport coverage is incomplete")
    require(all(not r.get("errors") for r in receipts), "Vue runtime errors were recorded")
    require(load(root, "embedded-layout-reports/diagnostics.json") == [], "Browser diagnostics are not clean")
    for key in ("credential_switch", "closed_authorization", "reset_confirmation_and_revision", "stale_probe"):
        require(layout.get(key) == "passed", "Browser interaction evidence missing: " + key)
    require(layout.get("configuration_drawers") == 11, "Tool drawer coverage is incomplete")
    for route, width, height in expected:
        require((root / f"embedded-layout-reports/{route[1:]}-{width}x{height}.png").is_file(), "Viewport screenshot missing")
    run = load(root, "core-stack-acceptance/platform-run.json")
    digest = run.get("artifact_sha256", "")
    require(run.get("status") == "READY" and bool(re.fullmatch(r"[a-f0-9]{64}", digest)), "Product run is not ready")
    for filename in ("product-stack.json", "cube-image-stack.json"):
        report = load(root, "core-stack-acceptance/" + filename)
        require(report.get("archive_sha256") == digest, "Product archive digest mismatch: " + filename)
        for key in ("full_stack", "frontend_build", "frontend_types", "upstream_auth", "redis_sessions", "business_owner_isolation"):
            require(report.get(key) == "passed", "Product acceptance missing: " + filename + ":" + key)
    require(load(root, "core-stack-acceptance/credential-audit.json").get("native_operation_log") == "passed", "Credential audit missing")
    require(load(root, "core-stack-acceptance/structurizr.json").get("structurizr_parser") == "passed", "Generated C4 parser evidence missing")
    parser = load(root, "c4-parser-contract/parser.json")
    require({r["case"] for r in parser} == {"english", "chinese", "special"} and all(r["exit_code"] == 0 for r in parser), "C4 parser contract failed")
    for name in ("coder-build", "coder-runtime", "cube-build", "cube-runtime", "cube-acceptance"):
        report = load(root, "integration-image-reports/" + name + ".json")
        require(report.get("status") == "passed" and report.get("exit_code") == 0 and not report.get("timeout"), "Image check failed: " + name)
    consoles = load(root, "tool-console-readiness/readiness.json")
    require(all(consoles.get(key) == "reachable" for key in ("coder", "litellm", "litellm_ui", "structurizr", "coder_workspace_network")), "Tool console/network check missing")
    require((root / "coder-template-lock/.terraform.lock.hcl").is_file(), "Validated Coder dependency lock missing")
    for name in ("host.uv.lock", "host.pyproject.toml"):
        require((root / "integration-image-reports" / name).is_file() and (root / "integration-image-reports" / name).stat().st_size > 0, "Tested host dependency lock is missing")
    return {"tests_passed": len(cases), "postgres_configuration_tests": pg, "viewport_cases": len(expected),
            "generated_product_sha256": digest}


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in name and bool(path.parts), "Unsafe archive path")
    require(not any(part == ".env" or (part.startswith(".env.") and part != ".env.example") for part in path.parts), "Private environment file in source")
    require(path.suffix.lower() not in {".ttf", ".otf", ".woff", ".woff2"}, "Standalone font file must not be distributed")
    return path.as_posix()


def package(root: Path, output: Path, commit: str, run_url: str) -> dict:
    summary = validate(root, commit)
    receipt = {"schema_version": 1, "source_commit": commit, "workflow_run": run_url,
               "scope": "single-host development and generated CRUD acceptance", "ci_acceptance": "passed",
               "production_ready": False, "live_model_authorization": "not_run", "live_cube_cluster": "not_run",
               "live_mcp_server": "not_run", "live_coder_provisioning": "not_run", **summary}
    payload = {}
    with tarfile.open(root / "contract-results/source-under-test.tar") as source:
        require(source.pax_headers.get("comment") == commit, "Source archive provenance mismatch")
        for entry in source:
            if entry.isdir():
                continue
            require(entry.isfile(), "Source links/devices are not allowed in the delivery archive")
            name = safe_name(entry.name)
            require(name not in payload, "Duplicate source file")
            payload[name] = (source.extractfile(entry).read(), entry.mode)
    require("RELEASE.json" in payload and "Dockerfile" in payload, "Source archive is incomplete")
    require("SOURCE_MANIFEST.sha256" not in payload, "Remove the stale tracked manifest before delivery")
    for name in ("host.uv.lock", "host.pyproject.toml"):
        data = (root / "integration-image-reports" / name).read_bytes()
        dest = "locks/" + name
        require(dest not in payload or payload[dest][0] == data, "Tracked dependency lock differs from the tested image")
        payload[dest] = (data, 0o644)
    receipt["dependency_lock"] = "locks/host.uv.lock from the same CI image build"
    manifest = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n" for name, (data, _) in sorted(payload.items()))
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output / "ai-rnd-foundation-source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, (data, mode) in sorted(payload.items()):
            info = zipfile.ZipInfo("ai-rnd-foundation/" + name)
            info.create_system = 3
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
        archive.writestr("ai-rnd-foundation/SOURCE_MANIFEST.sha256", manifest)
    with zipfile.ZipFile(output / "ai-rnd-foundation-evidence.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            require(not path.is_symlink(), "Evidence symlinks are not allowed")
            if path.is_file() and path.name != "source-under-test.tar":
                archive.write(path, safe_name(path.relative_to(root).as_posix()))
        archive.writestr("DELIVERY.json", json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    (output / "DELIVERY.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sums = "".join(hashlib.sha256((output / name).read_bytes()).hexdigest() + "  " + name + "\n"
                   for name in ("ai-rnd-foundation-source.zip", "ai-rnd-foundation-evidence.zip", "DELIVERY.json"))
    (output / "SHA256SUMS").write_text(sums, encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.evidence, args.output, args.source_commit, args.run_url), ensure_ascii=False, indent=2))

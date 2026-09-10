"""Delivery refuses partial, stale, unsafe or mismatched acceptance artifacts."""
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest

from scripts.build_delivery import DeliveryError, package, safe_name, validate

COMMIT = 'a' * 40
DIGEST = 'b' * 64


@pytest.fixture
def evidence(tmp_path):
    def write(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value))
    write('contract-results/source-commit.txt', COMMIT)
    write('contract-results/junit-ci.xml', '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="tests.test_tool_settings" name="revision[postgres]"/></testsuite></testsuites>')
    receipts = []
    for route in ('factory', 'factory-providers', 'factory-toolchain'):
        for width, height in ((1366, 768), (1280, 720), (820, 760), (390, 780)):
            receipts.append(dict(route='/' + route, width=width, height=height, errors=[]))
            write(f'embedded-layout-reports/{route}-{width}x{height}.png', 'test fixture, not a screenshot')
    write('embedded-layout-reports/layout.json', dict(receipts=receipts, credential_switch='passed', closed_authorization='passed', reset_confirmation_and_revision='passed', stale_probe='passed', configuration_drawers=11))
    write('embedded-layout-reports/diagnostics.json', [])
    write('core-stack-acceptance/platform-run.json', dict(status='READY', artifact_sha256=DIGEST))
    report = {key: 'passed' for key in ('full_stack', 'frontend_build', 'frontend_types', 'upstream_auth', 'redis_sessions', 'business_owner_isolation')}
    for name in ('product-stack.json', 'cube-image-stack.json'):
        write('core-stack-acceptance/' + name, dict(report, archive_sha256=DIGEST))
    write('core-stack-acceptance/credential-audit.json', {'native_operation_log': 'passed'})
    write('core-stack-acceptance/structurizr.json', {'structurizr_parser': 'passed'})
    write('c4-parser-contract/parser.json', [dict(case=case, exit_code=0) for case in ('english', 'chinese', 'special')])
    for name in ('coder-build', 'coder-runtime', 'cube-build', 'cube-runtime', 'cube-acceptance'):
        write('integration-image-reports/' + name + '.json', dict(status='passed', exit_code=0, timeout=False))
    write('tool-console-readiness/readiness.json', {key: 'reachable' for key in ('coder', 'litellm', 'coder_workspace_network')})
    write('coder-template-lock/.terraform.lock.hcl', '# unit fixture, not a provider lock')
    write('integration-image-reports/host.uv.lock', '# test dependency lock')
    write('integration-image-reports/host.pyproject.toml', '# test dependency manifest')
    with tarfile.open(tmp_path / 'contract-results/source-under-test.tar', 'w', format=tarfile.PAX_FORMAT, pax_headers={'comment': COMMIT}) as archive:
        for name, data in [('RELEASE.json', b'{}'), ('Dockerfile', b'# unit fixture'), ('scripts/start.sh', b'#!/bin/sh\n')]:
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o755 if name.endswith('.sh') else 0o644
            archive.addfile(entry, io.BytesIO(data))
    return tmp_path


def test_valid_package_preserves_scope_modes_and_hashes(evidence, tmp_path_factory):
    out = tmp_path_factory.mktemp('delivery')
    result = package(evidence, out, COMMIT, 'test-only')
    assert result['ci_acceptance'] == 'passed' and result['production_ready'] is False
    assert result['live_cube_cluster'] == 'not_run'
    with zipfile.ZipFile(out / 'ai-rnd-foundation-source.zip') as archive:
        assert archive.getinfo('ai-rnd-foundation/scripts/start.sh').external_attr >> 16 & 0o777 == 0o755
        assert archive.read('ai-rnd-foundation/locks/host.uv.lock') == b'# test dependency lock'
        assert '  Dockerfile\n' in archive.read('ai-rnd-foundation/SOURCE_MANIFEST.sha256').decode()
    assert len((out / 'SHA256SUMS').read_text().splitlines()) == 3


def test_stale_commit_is_rejected(evidence):
    with pytest.raises(DeliveryError, match='different commit'):
        validate(evidence, 'c' * 40)


@pytest.mark.parametrize('name,change', [
    ('embedded-layout-reports/layout.json', {'stale_probe': 'not_run'}),
    ('core-stack-acceptance/cube-image-stack.json', {'archive_sha256': 'c' * 64}),
    ('integration-image-reports/cube-build.json', {'exit_code': 1}),
    ('integration-image-reports/cube-runtime.json', {'timeout': True}),
    ('tool-console-readiness/readiness.json', {'coder_workspace_network': 'not_run'}),
])
def test_partial_evidence_is_rejected(evidence, name, change):
    path = evidence / name
    path.write_text(json.dumps(json.loads(path.read_text()) | change))
    with pytest.raises(DeliveryError):
        validate(evidence, COMMIT)


def test_skipped_junit_is_rejected(evidence):
    path = evidence / 'contract-results/junit-ci.xml'
    path.write_text(path.read_text().replace('skipped="0"', 'skipped="1"'))
    with pytest.raises(DeliveryError, match='skipped'):
        validate(evidence, COMMIT)


@pytest.mark.parametrize('path', ['../outside', '/absolute', 'a\\b', '.env', 'folder/.env.production', 'font.ttf'])
def test_unsafe_payload_name_is_rejected(path):
    with pytest.raises(DeliveryError):
        safe_name(path)

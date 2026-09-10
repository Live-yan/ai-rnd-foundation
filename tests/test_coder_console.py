"""Protect the upstream Coder image startup contract without credentials."""
from pathlib import Path

import yaml


def test_coder_uses_pinned_image_server_entrypoint_without_duplicate_command():
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / 'compose.tools.yaml').read_text(encoding='utf-8'))
    coder = config['services']['coder']
    assert coder['image'].startswith('ghcr.io/coder/coder@sha256:')
    assert len(coder['image'].split('sha256:')[1]) == 64
    assert not coder.get('command')
    assert 'entrypoint' not in coder
    assert coder['environment']['CODER_HTTP_ADDRESS'] == '0.0.0.0:7080'
    assert coder['depends_on']['tools-db-init']['condition'] == 'service_completed_successfully'

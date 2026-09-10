"""The diagnostics wrapper must preserve failures and not require app services."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.ci_capture import capture


def test_success_and_bounded_console_tail(tmp_path, capsys):
    assert capture('build', [sys.executable, '-c', 'for i in range(100): print("line-"+str(i))'], tmp_path) == 0
    assert len((tmp_path / 'build.log').read_text().splitlines()) == 100
    out = capsys.readouterr().out
    assert 'line-0\n' not in out and 'line-99\n' in out
    assert json.loads((tmp_path / 'build.json').read_text())['status'] == 'passed'


def test_failure_exit_status_is_preserved(tmp_path, capsys):
    assert capture('build', [sys.executable, '-c', 'import sys; print("::error::fixture"); sys.exit(7)'], tmp_path) == 7
    assert '::error::' not in capsys.readouterr().out
    assert json.loads((tmp_path / 'build.json').read_text())['exit_code'] == 7


def test_timeout_is_not_success(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('fixture', 1)
    monkeypatch.setattr('scripts.ci_capture.subprocess.run', timeout)
    assert capture('build', ['fixture'], tmp_path, timeout=1) == 124
    assert json.loads((tmp_path / 'build.json').read_text())['timeout'] is True


def test_unavailable_command_is_not_success(tmp_path):
    assert capture('build', ['/no-such-ci-command'], tmp_path) == 127
    assert json.loads((tmp_path / 'build.json').read_text())['status'] == 'failed'


@pytest.mark.parametrize('name', ['../escape', '/absolute', '', 'two words'])
def test_report_name_cannot_escape_directory(tmp_path, name):
    with pytest.raises(ValueError):
        capture(name, ['fixture'], tmp_path)

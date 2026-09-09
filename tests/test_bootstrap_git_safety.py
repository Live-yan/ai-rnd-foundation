"""Stdlib regression checks: python -m unittest discover -s tests -p test_bootstrap_git_safety.py"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import bootstrap


class BootstrapGitSafetyTests(unittest.TestCase):
    def test_git_trust_is_scoped_and_uses_command_line_config(self):
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path(directory)
            args = ['git', 'rev-parse', 'HEAD']
            with patch.object(bootstrap.subprocess, 'run') as execute:
                execute.return_value = subprocess.CompletedProcess(args, 0, 'commit\n', '')
                self.assertEqual(bootstrap.run(args, cwd), 'commit')
            command = execute.call_args.args[0]
            self.assertIn(f'safe.directory={cwd.resolve().as_posix()}', command)
            self.assertNotIn('safe.directory=*', command)
            self.assertNotIn('--global', command)
            self.assertEqual(args, ['git', 'rev-parse', 'HEAD'])

    def test_dirty_upstream_is_not_reset_or_cleaned(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(bootstrap, 'run', side_effect=[bootstrap.MANIFEST['commit'], ' M file']) as run:
                with self.assertRaisesRegex(RuntimeError, 'Preserve local edits'):
                    bootstrap.fetch_upstream(Path(directory))
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                self.assertNotIn('reset', call.args[0])
                self.assertNotIn('clean', call.args[0])


if __name__ == '__main__':
    unittest.main()

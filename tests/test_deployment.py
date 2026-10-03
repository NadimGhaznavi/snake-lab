"""Exercise deployment and migration in isolated directories with fake services."""

import ast
import os
from pathlib import Path
import pwd
import grp
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'prod/snakelab'
        self.legacy = self.root / 'old/snake-lab'
        scripts = self.root / 'scripts'
        scripts.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for command in ('systemctl', 'mariadb', 'getent', 'usermod', 'useradd'):
            self.executable(self.bin / command, '#!/bin/sh\nexit 0\n')
        rebuild = self.root / 'rebuild.sh'
        self.executable(rebuild, '#!/bin/sh\nset -e\n'
                        'test ! -f "${FAIL_REBUILD_FILE}"\n'
                        'printf rebuilt >"${REBUILD_FILE}"\n')
        common = (ROOT / 'scripts/deploy-common.sh').read_text()
        replacements = {
            '/opt/prod/snakelab': str(self.target),
            '/opt/snake-lab': str(self.legacy),
            '/etc/systemd/system/snake-lab.service': str(self.root / 'unit'),
            '/usr/local/bin/lab-client': str(self.root / 'client'),
            '/usr/local/bin/lab-viewer': str(self.root / 'viewer'),
            '-o root': '-o ' + pwd.getpwuid(os.getuid()).pw_name,
            '-o snake-lab': '-o ' + pwd.getpwuid(os.getuid()).pw_name,
            '-g snake-lab': '-g ' + grp.getgrgid(os.getgid()).gr_name,
            '${PROJECT_DIR}/scripts/rebuild-venv.sh': str(rebuild),
        }
        for old, new in replacements.items():
            common = common.replace(old, new)
        (scripts / 'deploy-common.sh').write_text(common)
        upgrade = (ROOT / 'scripts/upgrade.sh').read_text().replace(
            'readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"',
            'readonly PROJECT_DIR=' + shlex.quote(str(ROOT)))
        upgrade = upgrade.replace('\nrequire_root\n', '\n')
        upgrade = upgrade.replace('install -d -m 0755 /opt/prod',
                                  'install -d -m 0755 ' + shlex.quote(str(self.target.parent)))
        (scripts / 'upgrade.sh').write_text(upgrade)
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        REBUILD_FILE=str(self.root / 'rebuilt'),
                        FAIL_REBUILD_FILE=str(self.root / 'fail'))
        self.upgrade = scripts / 'upgrade.sh'

    def executable(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0o755)

    def installation(self, path):
        self.executable(path / 'venv/bin/python', '#!/bin/sh\nexit 0\n')
        (path / 'config').mkdir()
        (path / 'config/database.json').write_text('{"password":"preserved"}')
        (path / 'logs').mkdir()
        (path / 'logs/server.log').write_text('preserved log')
        (path / 'app').mkdir()
        for name in ('requirements.txt', 'requirements-torch-cpu.txt'):
            (path / name).write_bytes((ROOT / name).read_bytes())

    def run_upgrade(self):
        return subprocess.run(['bash', str(self.upgrade)], env=self.env,
                              capture_output=True, text=True)

    def assert_deployment(self):
        constants = self.target / 'snakelab/constants/DSnakeLab.py'
        module = ast.parse(constants.read_text())
        version = next(node.value.value for node in ast.walk(module)
                       if isinstance(node, ast.AnnAssign)
                       and isinstance(node.target, ast.Name) and node.target.id == 'VERSION')
        self.assertTrue(version)
        self.assertTrue((self.target / 'snakelab/client/client.tcss').is_file())
        self.assertTrue((self.target / 'snakelab/schemas/database-v4.sql').is_file())
        self.assertTrue((self.target / 'snakelab/server/SimulationServer.py').is_file())
        self.assertFalse((self.target / 'app').exists())
        loaded = subprocess.run(
            [sys.executable, '-c',
             'from snakelab.constants.DSnakeLab import DSnakeLab; '
             'from snakelab.server.Configuration import DEFAULT_SCHEMA_PATH; '
             'assert DEFAULT_SCHEMA_PATH.is_file(); print(DSnakeLab.VERSION)'],
            cwd=self.target, env=dict(self.env, PYTHONPATH=str(self.target)),
            capture_output=True, text=True)
        self.assertEqual(loaded.returncode, 0, loaded.stderr)
        self.assertEqual(loaded.stdout.strip(), version)
        self.assertEqual((self.target / 'config/database.json').read_text(),
                         '{"password":"preserved"}')
        self.assertEqual((self.target / 'logs/server.log').read_text(), 'preserved log')

    def test_migration_preserves_credentials_and_deploys_discoverable_package(self):
        self.installation(self.legacy)
        result = self.run_upgrade()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.legacy.exists())
        self.assertTrue((self.root / 'rebuilt').exists())
        self.assert_deployment()
        self.assertFalse((self.target / '.venv-needs-rebuild').exists())
        # A subsequent upgrade need not rebuild unchanged dependencies.
        (self.root / 'rebuilt').unlink()
        result = self.run_upgrade()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'rebuilt').exists())
        self.assert_deployment()

    def test_duplicate_installations_are_rejected_before_modification(self):
        self.installation(self.legacy)
        self.installation(self.target)
        result = self.run_upgrade()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Both', result.stderr)
        self.assertTrue((self.legacy / 'app').exists())
        self.assertTrue((self.target / 'app').exists())

    def test_failed_rebuild_can_be_retried_after_relocation(self):
        self.installation(self.legacy)
        (self.root / 'fail').touch()
        result = self.run_upgrade()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.target / '.venv-needs-rebuild').exists())
        self.assert_deployment()
        (self.root / 'fail').unlink()
        result = self.run_upgrade()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'rebuilt').exists())
        self.assertFalse((self.target / '.venv-needs-rebuild').exists())

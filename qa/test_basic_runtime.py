"""Basic startup, root configuration and module integration checks."""
import tempfile
import unittest
from unittest.mock import patch
from api.service.config import load, ROOT
from support_config import basic_api_configuration


class BasicRuntimeTests(unittest.TestCase):
    def test_startup_missing_tls_precedes_database_and_docker(self):
        from api.service import launcher
        with tempfile.TemporaryDirectory() as directory:
            root=basic_api_configuration(directory)
            settings=load(root)
            with patch.object(launcher,'load',return_value=settings),patch.object(launcher.database_runtime,'prepare',return_value=({},{})),patch.object(launcher.database_runtime,'owned_resources') as resources,patch.object(launcher.database_runtime,'docker') as docker:
                self.assertEqual(launcher.main(root,['--with-api']),1)
                resources.assert_not_called()
                docker.assert_not_called()

    def test_database_only_routes_to_original_launcher(self):
        import start
        with patch('sys.argv',['start.py','--database-only']),patch.object(start,'database_main',return_value=0) as database:
            self.assertEqual(start.main(),0)
            database.assert_called_once_with()

    def test_default_routes_to_combined_launcher(self):
        import start
        with patch('sys.argv',['start.py']),patch('api.service.launcher.main',return_value=0) as combined:
            self.assertEqual(start.main(),0)
            combined.assert_called_once_with(ROOT,['--with-api'])

    def test_fresh_check_creates_all_configuration_from_examples(self):
        from api.service import launcher
        with tempfile.TemporaryDirectory() as directory:
            root=basic_api_configuration(directory)
            (root/'modules/database').mkdir(parents=True)
            for relative in ('provisioning.example.jsonc','modules/database/config.example.jsonc'):
                (root/relative).write_text((ROOT/relative).read_text(encoding='utf-8'),encoding='utf-8')
            with patch.object(launcher.database_runtime,'docker') as docker:
                self.assertEqual(launcher.main(root,['--with-api','--check']),0)
                docker.assert_not_called()
            for relative in ('modules/api/config.jsonc','provisioning.jsonc','modules/database/config.jsonc'):
                self.assertTrue((root/relative).is_file())

    def test_api_check_does_not_read_secrets_or_mutate(self):
        from api.service import launcher
        with patch.object(launcher,'load',return_value={}),patch.object(launcher.database_runtime,'prepare',return_value=({},{})),patch.object(launcher,'administrative_setup') as privileged,patch.object(launcher.database_runtime,'docker') as docker:
            self.assertEqual(launcher.main(ROOT,['--api-migrate','--check']),0)
            privileged.assert_not_called()
            docker.assert_not_called()


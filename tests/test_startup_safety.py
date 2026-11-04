"""Safe startup diagnostics, independent cleanup, and Compose isolation."""
import contextlib
import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from app.cleanup import cleanup_actions
from app.config import PROJECT_ROOT, ConfigurationError, load_config
from app.database import DatabaseError, compose_command, start_postgres
from app.infrastructure import require_infrastructure
from start import main


class StartupSafetyTests(unittest.TestCase):
    def run_main(self, failure=None, close_failure=False, migration_failure=None):
        from modules.base import runtime
        config=json.loads((PROJECT_ROOT/".app.config.example").read_text())
        database=MagicMock();auth=MagicMock();logger=MagicMock()
        if close_failure:
            database.close.side_effect=RuntimeError("private-close-error")
            logger.close.side_effect=RuntimeError("private-log-close-error")
        output=io.StringIO()
        with contextlib.ExitStack() as stack:
            for name,value in (("load_config",config),("Database",database),("AuthService",auth),("ApplicationLogger",logger)):
                stack.enter_context(patch("modules.base.runtime."+name,return_value=value))
            stack.enter_context(patch("modules.base.runtime.Path.read_text",return_value="unit-only-secret"))
            stack.enter_context(patch("modules.base.runtime.load_signing_secret",return_value="unit-key"*8))
            stack.enter_context(patch("modules.base.runtime.APIUserStore"))
            stack.enter_context(patch("modules.base.runtime.create_app"))
            stack.enter_context(patch("modules.base.runtime.run_api",side_effect=failure))
            stack.enter_context(contextlib.redirect_stderr(output))
            stack.enter_context(contextlib.redirect_stdout(output))
            result=runtime.main([])
        return result,database,auth,logger,output.getvalue()


    def test_primary_error_and_cleanup_errors_are_safe(self):
        result,database,auth,logger,output=self.run_main(ValueError("password=never-log-primary"),True)
        self.assertEqual(result,1)
        database.close.assert_called_once();auth.close.assert_called_once();logger.close.assert_called_once()
        for secret in ("never-log-primary","private-close-error","private-log-close-error"):
            self.assertNotIn(secret,output)


    def test_cleanup_failure_changes_success_to_failure(self):
        self.assertEqual(self.run_main(close_failure=True)[0],1)

    def test_normal_ctrl_c_is_not_unexpected_error(self):
        result,*_,output=self.run_main(KeyboardInterrupt())
        self.assertEqual(result,0)
        self.assertIn("stopped by user",output)


    def test_broken_reporter_does_not_stop_cleanup(self):
        calls=[]
        def broken():calls.append("first");raise ValueError("not logged")
        def reporter(detail):raise RuntimeError("reporter failure")
        failures=cleanup_actions([("first",broken),("second",lambda:calls.append("second"))],reporter)
        self.assertEqual(calls,["first","second"])
        self.assertEqual(len(failures),1)

    def test_workspace_binding_and_explicit_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config={"infrastructure":{"project_name":"","workspace":""}}
            with self.assertRaises(ConfigurationError):require_infrastructure(config,root)
            config["infrastructure"]["project_name"]="derived-demo"
            self.assertEqual(require_infrastructure(config,root),"derived-demo")
            self.assertEqual(config["infrastructure"]["workspace"],str(root.resolve()))
            with tempfile.TemporaryDirectory() as copy:
                with self.assertRaises(ConfigurationError):require_infrastructure(config,Path(copy))
            command=compose_command(root,"derived-demo")
            self.assertEqual(command[command.index("--project-name")+1],"derived-demo")

    def test_other_workspace_container_cannot_be_reused(self):
        config=json.loads((PROJECT_ROOT/".app.config.example").read_text())
        inspected=[{"Config":{"Env":[],"Labels":{"com.docker.compose.project.working_dir":"C:/different/workspace"}}}]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch("app.database.run_command",side_effect=[MagicMock(stdout=b"container"),MagicMock(stdout=json.dumps(inspected).encode())]) as command:
                with self.assertRaisesRegex(DatabaseError,"owned by another"):
                    start_postgres(config["database"],root/"unused-secret",root,project="unit-project")
                self.assertEqual(command.call_count,2)

    def test_current_local_identity_and_volume_name_are_ouroboros(self):
        # Read only the tracked template, never another project's local preferences.
        config=json.loads((PROJECT_ROOT/".app.config.example").read_text(encoding="utf-8"))
        self.assertEqual(require_infrastructure(config),"ouroboros")
        self.assertEqual(config["auth"]["issuer"],"ouroboros")
        self.assertEqual(config["auth"]["audience"],"ouroboros-api")
        self.assertEqual(config["database"]["name"],"")
        self.assertEqual(config["database"]["user"],"")
        compose=(PROJECT_ROOT/"compose.yaml").read_text()
        self.assertIn("postgres_data:/var/lib/postgresql/data",compose)
        self.assertIn("OUROBOROS_DB_SECRET_FILE",compose)
        self.assertNotIn("name: foundation",compose)


    def test_unowned_volume_without_container_is_not_adopted(self):
        config=json.loads((PROJECT_ROOT/".app.config.example").read_text())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch("app.database.run_command",side_effect=[MagicMock(stdout=b""),MagicMock(stdout=b"other_project_postgres_data")]) as command:
                with self.assertRaisesRegex(DatabaseError,"automatic adoption is disabled"):
                    start_postgres(config["database"],root/"unused-secret",root,"other_project")
                self.assertEqual(command.call_count,2)

    def test_logger_attempts_all_handler_closures(self):
        from app.logger import ApplicationLogger
        from app.cleanup import ResourceCleanupError
        with tempfile.TemporaryDirectory() as directory:
            config=json.loads((PROJECT_ROOT/".app.config.example").read_text())
            logger=ApplicationLogger(config["logging"],root=Path(directory),stream=io.StringIO())
            first,second=logger.logger.handlers
            original=first.close
            first.close=MagicMock(side_effect=RuntimeError("private handler detail"))
            with patch.object(second,"close",wraps=second.close) as close_file:
                with self.assertRaises(ResourceCleanupError):logger.close()
                close_file.assert_called_once()
            first.close=original
            original()
            self.assertEqual(logger.logger.handlers,[])


    def test_migration_failure_is_not_masked_by_connection_cleanup(self):
        from modules.base.runtime import migrate_with_cleanup
        connection=MagicMock();connection.close.side_effect=RuntimeError("private-close-error")
        original=ValueError("private-migration-message")
        with patch("modules.base.runtime.connect",return_value=connection), patch("modules.base.runtime.migrate",side_effect=original):
            with self.assertRaises(ValueError) as raised:migrate_with_cleanup({},"disposable")
        self.assertIs(raised.exception,original)
        connection.close.assert_called_once()

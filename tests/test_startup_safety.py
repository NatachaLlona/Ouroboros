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
        config=json.loads((PROJECT_ROOT/".app.config.example").read_text())
        config["infrastructure"]["project_name"]="startup-unit"
        logger=MagicMock()
        events=[]
        logger.log.side_effect=lambda event: events.append(event)
        database=MagicMock();auth=MagicMock()
        if close_failure:
            database.close.side_effect=RuntimeError("private-close-error")
            logger.close.side_effect=RuntimeError("private-log-close-error")
        stream=io.StringIO();handler=logging.StreamHandler(stream)
        handler_close=MagicMock(wraps=handler.close)
        handler.close=handler_close
        with contextlib.ExitStack() as stack:
            for name,value in (("load_config",config),("ApplicationLogger",logger),("Database",database),("AuthService",auth)):
                stack.enter_context(patch("start."+name,return_value=value))
            for name in ("check_docker","prompt_credentials","write_secret","start_postgres","ensure_database","connect","migrate","APIUserStore","configure_api_credentials","load_signing_secret","create_app"):
                mocked=stack.enter_context(patch("start."+name))
                if migration_failure is not None and name=="migrate": mocked.side_effect=migration_failure
                if migration_failure is not None and name=="connect": mocked.return_value.close.side_effect=RuntimeError("private-connection-close")
            stack.enter_context(patch("start.logging.StreamHandler",return_value=handler))
            stack.enter_context(patch("start.run_api",side_effect=failure))
            result=main()
        return result,events,database,auth,logger,handler_close,stream.getvalue()

    def test_primary_error_and_cleanup_errors_are_safe(self):
        result,events,database,auth,logger,handler,output=self.run_main(ValueError("password=never-log-primary"),True)
        self.assertEqual(result,1)
        database.close.assert_called_once();auth.close.assert_called_once();logger.close.assert_called_once();handler.assert_called_once()
        primary=next(event for event in events if event.get("context",{}).get("error_type")=="ValueError")
        self.assertEqual(primary["context"]["stage"],"api_server")
        self.assertTrue(primary["context"]["frames"])
        for frame in primary["context"]["frames"]:
            self.assertEqual(set(frame),{"source","line","function"})
        serialized=json.dumps(events)+output
        for secret in ("never-log-primary","private-close-error","private-log-close-error"):
            self.assertNotIn(secret,serialized)
        self.assertNotIn("data was preserved",serialized.lower())

    def test_cleanup_failure_changes_success_to_failure(self):
        self.assertEqual(self.run_main(close_failure=True)[0],1)

    def test_normal_ctrl_c_is_not_unexpected_error(self):
        result,events,*_=self.run_main(KeyboardInterrupt())
        self.assertEqual(result,0)
        self.assertFalse(any(event["level"]=="ERROR" for event in events if "level" in event))
        self.assertTrue(any(event["message"]=="Application stopped by user" for event in events))

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

    def test_current_local_identity_and_volume_name_remain_foundation(self):
        # Read only public identity settings; never output the local account preferences.
        config={"infrastructure":{"project_name":"foundation","workspace":str(PROJECT_ROOT)}}
        self.assertEqual(require_infrastructure(config),"foundation")
        compose=(PROJECT_ROOT/"compose.yaml").read_text()
        self.assertIn("postgres_data:/var/lib/postgresql/data",compose)
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
        result,events,*_=self.run_main(migration_failure=ValueError("private-migration-message"))
        self.assertEqual(result,1)
        self.assertTrue(any(event.get("context",{}).get("stage")=="migrations" and event["context"].get("error_type")=="ValueError" for event in events))
        self.assertTrue(any(event.get("context",{}).get("resource")=="migration_connection" for event in events))
        self.assertNotIn("private-migration-message",json.dumps(events))
        self.assertNotIn("private-connection-close",json.dumps(events))

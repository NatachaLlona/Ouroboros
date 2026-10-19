"""Credential, configuration, Docker failure, and migration unit checks."""
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.config import PROJECT_ROOT, ConfigurationError, load_config
from app.credentials import _read_masked, prompt_credentials, write_secret
from app.database import DatabaseError, check_docker, connect, start_postgres
from app.migrate import migrate
from start import main


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = json.loads((PROJECT_ROOT / ".app.config.example").read_text())
        self.config["logging"]["directory"] = str(self.root / "logs")
        self.config["infrastructure"]["project_name"] = "unit-database"

    def test_mask_backspace_and_cancel(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(_read_masked(iter("ab\bc\r").__next__, []), "ac")
            with self.assertRaises(KeyboardInterrupt):
                _read_masked(iter("secret\x03").__next__, [])
        self.assertNotIn("secret", output.getvalue())
        self.assertNotIn("ac", output.getvalue())

    def test_prompt_and_preserve_configuration(self):
        self.config["custom"] = "preserved"
        with patch("app.credentials.sys.stdin.isatty", return_value=True), \
             patch("builtins.input", side_effect=["test_database", "test_master"]), \
             patch("app.credentials.read_password", return_value="unit-only"):
            self.assertEqual(prompt_credentials(self.config, self.root), "unit-only")
        saved = json.loads((self.root / ".app.config").read_text())
        self.assertEqual(saved["database"]["user"], "test_master")
        self.assertEqual(saved["custom"], "preserved")
        self.assertNotIn("unit-only", (self.root / ".app.config").read_text())
        with patch("app.credentials.sys.stdin.isatty", return_value=True), \
             patch("builtins.input", side_effect=["n", "invalid user"]), patch("app.credentials.read_password"):
            with self.assertRaises(DatabaseError):
                prompt_credentials(self.config, self.root)

    def test_restricted_secret_is_not_replaced(self):
        path = write_secret("initial-unit-only", self.root)
        self.assertEqual(write_secret("wrong-unit-only", self.root), path)
        self.assertEqual(path.read_text(), "initial-unit-only")
        if __import__("os").name == "nt":
            result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                "$acl = Get-Acl -LiteralPath $env:TEST_SECRET_PATH; "
                "$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
                "if (-not $acl.AreAccessRulesProtected) { exit 1 }; "
                "foreach ($rule in $acl.Access) { if ($rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -ne $sid) { exit 2 } }"],
                env={**__import__("os").environ, "TEST_SECRET_PATH": str(path.parent)}, capture_output=True)
            self.assertEqual(result.returncode, 0)

    def test_database_field_validation(self):
        for field, value in (("port", True), ("port", 6969), ("startup_timeout", 0),
                             ("connect_timeout", "10"), ("statement_timeout", -1), ("name", "bad;name")):
            config = json.loads(json.dumps(self.config))
            config["database"][field] = value
            (self.root / ".app.config").write_text(json.dumps(config))
            with self.assertRaises(ConfigurationError):
                load_config(self.root)

    def test_unavailable_docker_logs_safe_failure(self):
        with patch("app.database.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(DatabaseError, "Docker CLI"):
                check_docker()
        output = io.StringIO()
        with patch("start.load_config", return_value=self.config), \
             patch("start.check_docker", side_effect=DatabaseError("Docker Engine is unavailable; open Docker Desktop")), \
             patch("start.prompt_credentials") as prompt, contextlib.redirect_stderr(output):
            self.assertEqual(main(), 1)
            prompt.assert_not_called()
        content = next((self.root / "logs").glob("*.log")).read_text()
        self.assertIn("open Docker Desktop", content)
        self.assertNotIn("preparation completed", content)

    def test_container_initialization_is_preserved_when_selecting_another_database(self):
        database = {**self.config["database"], "name": "new_name", "user": "new_master"}
        existing = json.dumps([{"Config": {"Labels": {"com.docker.compose.project.working_dir": str(self.root)}, "Env": ["POSTGRES_DB=old_name", "POSTGRES_USER=old_master"]}}]).encode()
        with patch("app.database.run_command", side_effect=[MagicMock(stdout=b"container"), MagicMock(stdout=existing), MagicMock()]) as run:
            start_postgres(database, self.root / "secret", self.root, "unit-database")
            self.assertEqual(run.call_args.args[2]["FOUNDATION_DB_NAME"], "old_name")
            self.assertEqual(run.call_args.args[2]["FOUNDATION_DB_USER"], "old_master")

    def test_invalid_credentials_do_not_leak(self):
        import psycopg
        with patch("psycopg.connect", side_effect=psycopg.OperationalError("private-password")):
            with self.assertRaises(DatabaseError) as result:
                connect(self.config["database"], "private-password")
        self.assertNotIn("private-password", str(result.exception))

    def test_changed_migration_is_rejected(self):
        (self.root / "sql/migrations").mkdir(parents=True)
        (self.root / "sql/migrations/001_create_test.sql").write_text("SELECT 1")
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("changed-checksum",)
        with self.assertRaisesRegex(DatabaseError, "modified"):
            migrate(connection, self.root)


if __name__ == "__main__":
    unittest.main()

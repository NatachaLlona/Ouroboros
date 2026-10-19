"""Isolated infrastructure checks; no examples are written to project logs."""
import contextlib
import io
import json
import logging
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app.config import ConfigurationError, PROJECT_ROOT, load_config
from app.logger import ApplicationLogger
from app.request_context import request_context, RequestContext, create_interaction_id
from start import main


class InfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.example = (PROJECT_ROOT / ".app.config.example").read_text(encoding="utf-8")
        (self.root / ".app.config.example").write_text(self.example, encoding="utf-8")
        self.config = json.loads(self.example)
        self.config["logging"]["level"] = "INFO"
        self.config["infrastructure"]["project_name"] = "unit-foundation"

    def save(self):
        (self.root / ".app.config").write_text(json.dumps(self.config), encoding="utf-8")

    def logger(self):
        self.console = io.StringIO()
        logger = ApplicationLogger(self.config["logging"], root=self.root, stream=self.console)
        self.addCleanup(logger.close)
        return logger

    def test_creation_and_preservation(self):
        self.assertEqual(load_config(self.root)["port"], 6969)
        self.config["port"] = 9000
        self.save()
        self.assertEqual(load_config(self.root)["port"], 9000)

    def test_hosts(self):
        for host in (None, "", "   "):
            self.config["host"] = host
            self.save()
            self.assertEqual(load_config(self.root)["host"], "localhost")
        del self.config["host"]
        self.save()
        self.assertEqual(load_config(self.root)["host"], "localhost")

    def test_invalid_configuration(self):
        for port in (0, 65536, True, "8087", 1.5, None):
            self.config["port"] = port
            self.save()
            with self.assertRaisesRegex(ConfigurationError, "port"):
                load_config(self.root)
        self.config["port"] = 8087
        for level in ("INVALID", [], None):
            self.config["logging"]["level"] = level
            self.save()
            with self.assertRaisesRegex(ConfigurationError, "logging.level"):
                load_config(self.root)
        (self.root / ".app.config").write_text("{invalid", encoding="utf-8")
        with self.assertRaises(ConfigurationError):
            load_config(self.root)

    def test_general_interaction_origin_and_outputs(self):
        logger = self.logger()
        line = sys._getframe().f_lineno + 1
        logger.log({"message": "General event"})
        token = request_context.set(RequestContext(create_interaction_id(), "GET", "/test"))
        logger.log({"message": "First", "interaction_id": "INT-0001", "context": {"entry_id": "WK0001"}})
        logger.log({"message": "Second", "interaction_id": "INT-0001"})
        request_context.reset(token)
        logger.log({"level": "DEBUG", "message": "Hidden"})
        lines = self.console.getvalue().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("application", lines[0])
        self.assertIn(f"test_infrastructure.py:{line}", lines[0])
        self.assertIn("InfrastructureTests", lines[0])
        self.assertIsNotNone(datetime.fromisoformat(lines[0].split(" | ")[2]).tzinfo)
        self.assertTrue(all(entry.split(" | ")[1].strip().isdigit() for entry in lines[1:]))
        self.assertEqual(lines[0].split(" | ")[1], " " * 24)
        self.assertEqual(next((self.root / "logs").glob("*.log")).read_text(encoding="utf-8"), self.console.getvalue())

    def test_levels_and_no_duplicate_handlers(self):
        first = self.logger()
        first.log({"message": "Once"})
        first.close()
        logger = self.logger()
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            logger.log({"level": level, "message": level})
        self.assertEqual(len(self.console.getvalue().splitlines()), 4)
        self.assertEqual(len(next((self.root / "logs").glob("*.log")).read_text(encoding="utf-8").splitlines()), 5)

    def test_single_line_and_custom_format(self):
        self.config["logging"]["format"] = "%(interaction_id)s %(message)s %(context)s"
        logger = self.logger()
        logger.log({"message": "Hello\nFORGED\r\x00\u2028", "interaction_id": "INT\n2", "context": {"value": "?\n"}})
        self.assertEqual(len(self.console.getvalue().splitlines()), 1)
        self.assertIn("FORGED", self.console.getvalue())
        self.assertNotIn("\x00", self.console.getvalue())

    def test_daily_rollover_and_append(self):
        logger = self.logger()
        handler = logger.logger.handlers[1]
        now = datetime.now().astimezone()
        for instant in (now, now + timedelta(days=1), now):
            record = logging.makeLogRecord({"created": instant.timestamp(), "msg": "daily"})
            handler.setFormatter(logging.Formatter("%(message)s"))
            handler.handle(record)
        paths = sorted((self.root / "logs").glob("*.log"))
        self.assertEqual(len(paths), 2)
        self.assertEqual(sorted(len(path.read_text().splitlines()) for path in paths), [1, 2])

    def test_bootstrap_failure_and_valid_run(self):
        output = io.StringIO()
        with patch("start.load_config", side_effect=ConfigurationError("port is invalid")), contextlib.redirect_stderr(output):
            self.assertEqual(main(), 1)
        self.assertIn("port", output.getvalue())
        self.config["logging"]["directory"] = str(self.root / "logs")
        with patch("start.load_config", return_value=self.config), \
             patch("start.check_docker"), patch("start.prompt_credentials", return_value="test-only"), \
             patch("start.write_secret"), patch("start.start_postgres"), \
             patch("start.connect"), patch("start.migrate"), patch("start.ensure_database"), \
             patch("start.configure_api_credentials"), patch("start.APIUserStore"), patch("start.AuthService"), patch("start.load_signing_secret", return_value="unit-signing-key" * 4), \
             patch("start.run_api"), contextlib.redirect_stderr(output):
            self.assertEqual(main(), 0)
        self.assertIn("Foundation preparation completed", output.getvalue())

    def test_execution_from_another_directory(self):
        # Copy the real entry point and modules to avoid modifying local configuration.
        import shutil
        (self.root / "check_config.py").write_text(
            "from app.config import load_config\nfrom app.logger import ApplicationLogger\n"
            "config = load_config()\nlogger = ApplicationLogger(config['logging'])\n"
            "logger.log({'message': 'Configuration verified'})\nlogger.close()\n", encoding="utf-8")
        shutil.copytree(PROJECT_ROOT / "app", self.root / "app", ignore=shutil.ignore_patterns("__pycache__"))
        with tempfile.TemporaryDirectory() as other:
            result = subprocess.run([sys.executable, str(self.root / "check_config.py")], cwd=other, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / ".app.config").exists())
        self.assertTrue((self.root / "logs").exists())
        self.config["port"] = -1
        self.save()
        result = subprocess.run([sys.executable, str(self.root / "check_config.py")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("port", result.stderr)


if __name__ == "__main__":
    unittest.main()

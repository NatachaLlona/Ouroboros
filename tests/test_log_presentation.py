"""Unicode, structured bodies, safe colors, and visible column widths."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import PROJECT_ROOT
from app.console import prepare_console, supports_color
from app.log_safety import body_preview
from app.logger import ApplicationLogger
from app.request_context import RequestContext, request_context

TEXT = "Ouroboros est\u00e1 vivo! \U0001f40d\U0001f4bb"


class LogPresentationTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root=Path(directory.name)
        self.config=json.loads((PROJECT_ROOT/".app.config.example").read_text())

    def test_unicode_object_context_widths_and_single_line(self):
        stream=io.StringIO()
        logger=ApplicationLogger(self.config["logging"],root=self.root,stream=stream)
        try:
            logger.log({"message":"Application ready"})
            token=request_context.set(RequestContext("202610181133110482759163","POST","/test"))
            try:
                preview=body_preview(json.dumps({"value":TEXT,"nested":[{"password":"never-show"}]}).encode(),2048)
                logger.log({"level":"DEBUG","message":"Request JSON body received","context":preview})
                logger.log({"message":"Control characters","context":{"value":"first\nFORGED\r\x1b[31m"}})
            finally:request_context.reset(token)
            lines=stream.getvalue().splitlines()
            self.assertEqual(len(lines),3)
            self.assertEqual(lines[0].split(" | ")[0],"INFO    ")
            self.assertEqual(lines[0].split(" | ")[1]," "*24)
            self.assertEqual(lines[1].split(" | ")[0],"DEBUG   ")
            self.assertEqual(lines[1].split(" | ")[1],"202610181133110482759163")
            self.assertEqual(lines[1].split(" | ")[3],"request    ")
            self.assertEqual(lines[0].split(" | ")[3],"application")
            context=json.loads(lines[1].split(" | ")[-1])
            self.assertEqual(context["body"]["value"],TEXT)
            self.assertIsInstance(context["body"],dict)
            self.assertIn(TEXT,lines[1])
            self.assertNotIn("\\u00e1",lines[1])
            self.assertNotIn("never-show",stream.getvalue())
            self.assertNotIn("\x1b",stream.getvalue())
            file=next((self.root/"logs").glob("*.log")).read_text(encoding="utf-8")
            self.assertEqual(file,stream.getvalue())
        finally:logger.close()

    def test_truncation_preserved_and_redaction_before_preview(self):
        preview=body_preview(json.dumps({"password":"never-show","value":TEXT*100}).encode(),64)
        self.assertTrue(preview["truncated"])
        self.assertLessEqual(len(preview["body_preview"]),64)
        self.assertNotIn("never-show",json.dumps(preview))
        self.assertIn("[REDACTED]",preview["body_preview"])

    def test_color_only_level_and_never_in_file(self):
        stream=io.StringIO()
        logger=ApplicationLogger(self.config["logging"],root=self.root,stream=stream)
        try:
            with patch("app.console.supports_color",return_value=True):
                for level in ("DEBUG","INFO","WARNING","ERROR","CRITICAL"):
                    logger.log({"level":level,"message":TEXT})
            for line in stream.getvalue().splitlines():
                first,*rest=line.split(" | ")
                self.assertIn("\x1b[",first)
                self.assertNotIn("\x1b", " | ".join(rest))
            file=next((self.root/"logs").glob("*.log")).read_text(encoding="utf-8")
            self.assertNotIn("\x1b",file)
            self.assertIn(TEXT,file)
            self.assertEqual(len(file.splitlines()),5)
        finally:logger.close()

    def test_no_color_redirect_and_utf8_stream(self):
        self.assertFalse(supports_color(io.StringIO()))
        class Terminal(io.StringIO):
            def isatty(self):return True
        with patch.dict("os.environ",{"NO_COLOR":""}):
            self.assertFalse(supports_color(Terminal()))
        with patch.dict("os.environ",{"TERM":"dumb"}):
            self.assertFalse(supports_color(Terminal()))
        buffer=io.BytesIO()
        stream=io.TextIOWrapper(buffer,encoding="ascii")
        prepare_console(stream).write(TEXT)
        stream.flush()
        self.assertEqual(buffer.getvalue().decode("utf-8"),TEXT)

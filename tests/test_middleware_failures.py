"""ASGI boundary failures must not create a second response or leak context."""
import asyncio
import io
import json
import tempfile
import unittest
import traceback
from pathlib import Path

from app.config import PROJECT_ROOT
from app.logger import ApplicationLogger, active_logger
from app.main import RequestLoggingMiddleware
from app.request_context import request_context


class MiddlewareFailureTests(unittest.TestCase):
    def test_before_and_after_response_start(self):
        async def check(started):
            with tempfile.TemporaryDirectory() as directory:
                output = io.StringIO()
                config = json.loads((PROJECT_ROOT/".app.config.example").read_text())["logging"]
                logger = ApplicationLogger(config, root=Path(directory), stream=output)
                messages = []
                secret = "private-unhandled-error-content"
                async def downstream(scope, receive, send):
                    if started:
                        await send({"type": "http.response.start", "status": 200, "headers": []})
                        await send({"type": "http.response.body", "body": b"partial", "more_body": True})
                    raise RuntimeError(secret)
                async def receive():
                    return {"type": "http.request", "body": b""}
                async def send(message):
                    messages.append(message)
                previous_context = request_context.get()
                previous_logger = active_logger.get()
                middleware = RequestLoggingMiddleware(downstream, logger)
                scope = {"type": "http", "method": "GET", "path": "/failure", "headers": []}
                try:
                    if started:
                        with self.assertRaises(RuntimeError) as failure:
                            await middleware(scope, receive, send)
                        self.assertNotIn(secret, "".join(traceback.format_exception(failure.exception)))
                    else:
                        await middleware(scope, receive, send)
                    starts = [m for m in messages if m["type"] == "http.response.start"]
                    self.assertEqual(len(starts), 1)
                    self.assertEqual(starts[0]["status"], 200 if started else 500)
                    self.assertTrue(dict(starts[0]["headers"])[b"x-interaction-id"])
                    self.assertEqual(output.getvalue().count("Unhandled request failure"), 1)
                    self.assertNotIn(secret, output.getvalue())
                    final = next(line for line in output.getvalue().splitlines() if "HTTP request finished" in line)
                    details = json.loads(final.split(" | ")[-1])
                    self.assertEqual(details["outcome"], "failed")
                    self.assertEqual(details["status"], 200 if started else 500)
                    self.assertTrue(details["response_started"])
                    self.assertEqual(request_context.get(), previous_context)
                    self.assertEqual(active_logger.get(), previous_logger)
                finally:
                    logger.close()
        for started in (False, True):
            asyncio.run(check(started))

    def test_expected_error_and_unsent_cancel_outcomes(self):
        async def check(cancel):
            with tempfile.TemporaryDirectory() as directory:
                output = io.StringIO()
                config = json.loads((PROJECT_ROOT/".app.config.example").read_text())["logging"]
                logger = ApplicationLogger(config, root=Path(directory), stream=output)
                async def downstream(scope, receive, send):
                    if cancel:
                        raise asyncio.CancelledError
                    await send({"type": "http.response.start", "status": 403, "headers": []})
                    await send({"type": "http.response.body", "body": b"denied"})
                async def receive(): return {"type": "http.request", "body": b""}
                async def send(message): pass
                try:
                    middleware = RequestLoggingMiddleware(downstream, logger)
                    if cancel:
                        with self.assertRaises(asyncio.CancelledError):
                            await middleware({"type": "http", "method": "GET", "path": "/outcome", "headers": []}, receive, send)
                    else:
                        await middleware({"type": "http", "method": "GET", "path": "/outcome", "headers": []}, receive, send)
                    final = next(line for line in output.getvalue().splitlines() if "HTTP request finished" in line)
                    details = json.loads(final.split(" | ")[-1])
                    self.assertEqual(details["outcome"], "cancelled" if cancel else "completed")
                    self.assertEqual(details["status"], None if cancel else 403)
                    self.assertEqual(details["response_started"], not cancel)
                finally:
                    logger.close()
        for cancel in (False, True): asyncio.run(check(cancel))

    def test_transport_failure_keeps_unsent_status_and_safe_propagation(self):
        async def check():
            with tempfile.TemporaryDirectory() as directory:
                output = io.StringIO()
                config = json.loads((PROJECT_ROOT/".app.config.example").read_text())["logging"]
                logger = ApplicationLogger(config, root=Path(directory), stream=output)
                attempts = []
                async def downstream(scope, receive, send):
                    await send({"type": "http.response.start", "status": 200, "headers": []})
                async def receive(): return {"type": "http.request", "body": b""}
                async def send(message):
                    attempts.append(message)
                    raise RuntimeError("private-transport-detail")
                try:
                    middleware = RequestLoggingMiddleware(downstream, logger)
                    with self.assertRaises(RuntimeError) as failure:
                        await middleware({"type":"http", "method":"GET", "path":"/transport", "headers":[]}, receive, send)
                    self.assertEqual(len(attempts), 1)
                    self.assertNotIn("private-transport-detail", "".join(traceback.format_exception(failure.exception)))
                    final = next(line for line in output.getvalue().splitlines() if "HTTP request finished" in line)
                    context = json.loads(final.split(" | ")[-1])
                    self.assertEqual(context["outcome"], "failed")
                    self.assertIsNone(context["status"])
                    self.assertFalse(context["response_started"])
                finally: logger.close()
        asyncio.run(check())

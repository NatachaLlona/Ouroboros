"""Overlapping ASGI requests, cleanup, filtering, redaction, and bounded connections."""
import asyncio
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import httpx
from app.config import PROJECT_ROOT, ConfigurationError, validate_logging
from app.database import Database
from app.logger import ApplicationLogger, log_event
from app.main import create_app, RequestLoggingMiddleware
from app.request_context import request_context, RequestContext, create_interaction_id


class LoggingConcurrencyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = json.loads((PROJECT_ROOT / ".app.config.example").read_text())
        self.config["logging"]["body_max_chars"] = 128
        self.output = io.StringIO()
        self.logger = ApplicationLogger(self.config["logging"], root=self.root, stream=self.output)
        self.addCleanup(self.logger.close)

    def test_overlapping_requests_context_body_and_general_events(self):
        app = create_app(self.config, None, None, self.logger)
        active = 0
        peak = 0
        lock = Lock()
        @app.post("/overlap/{index}")
        def overlap(index: int, body: dict):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                log_event("DEBUG", "Internal stage entered", component="probe")
                time.sleep(0.03)
                log_event("INFO", "Internal operation completed", component="probe")
                return {"index": index, "body": body}
            finally:
                with lock:
                    active -= 1
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                body={"nested": [{"password": "never-log-password", "access_token": "never-log-token"}], "value": "x" * 500}
                responses=await asyncio.gather(*(client.post(f"/overlap/{index}",json=body) for index in range(12)))
                self.assertIsNone(request_context.get())
                return responses
        responses=asyncio.run(run())
        self.assertGreater(peak,1)
        ids=[response.headers["X-Interaction-ID"] for response in responses]
        self.assertEqual(len(set(ids)),12)
        for index,response in enumerate(responses):
            self.assertEqual(response.json()["body"]["value"],"x" * 500)
            interaction=ids[index]
            self.assertRegex(interaction,r"^[0-9]{24}$")
            lines=[line for line in self.output.getvalue().splitlines() if interaction in line]
            self.assertTrue(lines)
            self.assertTrue(all(line.split(" | ")[1] == interaction and line.split(" | ")[3].strip() == "request" and line.split(" | ")[4] == f"POST /overlap/{index}" for line in lines))
            self.assertEqual(sum("Request JSON body received" in line for line in lines),1)
        self.assertNotIn("never-log-password",self.output.getvalue())
        self.assertNotIn("never-log-token",self.output.getvalue())
        self.assertIn("[REDACTED]",self.output.getvalue())
        self.assertIn('"truncated": true',self.output.getvalue())
        self.logger.log({"message":"Outside request"})
        fields=self.output.getvalue().splitlines()[-1].split(" | ")
        self.assertEqual(fields[1]," " * 24)
        self.assertEqual(fields[3],"application")
        self.assertEqual(fields[4],"")

    def test_cleanup_after_error_and_cancellation(self):
        async def run():
            async def fail(scope,receive,send):
                raise RuntimeError("private details")
            middleware=RequestLoggingMiddleware(fail,self.logger)
            async def receive(): return {"type":"http.request","body":b""}
            async def send(message): pass
            scope={"type":"http","method":"GET","path":"/failure","headers":[]}
            await middleware(scope,receive,send)
            self.assertIsNone(request_context.get())
            async def cancel(scope,receive,send): raise asyncio.CancelledError
            middleware=RequestLoggingMiddleware(cancel,self.logger)
            with self.assertRaises(asyncio.CancelledError):
                await middleware({**scope,"state":{}},receive,send)
            self.assertIsNone(request_context.get())
        asyncio.run(run())
        self.assertNotIn("private details",self.output.getvalue())
        self.assertIn('"status": null',self.output.getvalue())
        self.assertIn('"outcome": "cancelled"',self.output.getvalue())

    def test_levels_and_validation(self):
        for configured,count in (("INFO",4),("DEBUG",5)):
            output=io.StringIO()
            config={**self.config["logging"],"level":configured}
            logger=ApplicationLogger(config,root=self.root/configured,stream=output)
            try:
                for level in ("DEBUG","INFO","WARNING","ERROR","CRITICAL"):
                    logger.log({"level":level,"message":level})
            finally: logger.close()
            self.assertEqual(len(output.getvalue().splitlines()),count)
            self.assertIn("ERROR",output.getvalue())
            self.assertIn("CRITICAL",output.getvalue())
        for level in ("WARNING","ERROR","CRITICAL","invalid"):
            with self.assertRaises(ConfigurationError): validate_logging({**self.config["logging"],"level":level})

    def test_connection_limit_and_release(self):
        active=peak=0
        lock=Lock()
        @contextmanager
        def connection(*args):
            nonlocal active,peak
            with lock: active+=1; peak=max(peak,active)
            try: yield object()
            finally:
                with lock: active-=1
        database=Database({"max_connections":2,"connection_acquire_timeout":2},"not-a-real-password")
        def operation(index):
            with database.connection(): time.sleep(0.02)
        with patch("app.database.connect",side_effect=connection):
            with ThreadPoolExecutor(max_workers=8) as executor: list(executor.map(operation,range(16)))
        self.assertEqual(peak,2)
        self.assertEqual(active,0)
        database.close()


if __name__ == "__main__": unittest.main()

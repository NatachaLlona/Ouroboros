"""Opt-in real PostgreSQL checks using resources created solely by this test."""
import json
import os
import secrets
import shutil
import socket
import tempfile
import unittest
import uuid
from pathlib import Path

from app.config import PROJECT_ROOT
from app.credentials import write_secret
from app.database import (DatabaseError, check_docker, compose_command,
                          compose_environment, connect, run_command, start_postgres)
from app.database_test import insert_entry, read_entry
from app.migrate import migrate


@unittest.skipUnless(os.environ.get("FOUNDATION_RUN_INTEGRATION") == "1", "Set FOUNDATION_RUN_INTEGRATION=1 for an isolated Docker test")
class PostgreSQLIntegrationTests(unittest.TestCase):
    def test_first_run_persistence_identity_long_text_and_invalid_credentials(self):
        check_docker()
        project = "foundation-test-" + uuid.uuid4().hex
        root = Path(tempfile.mkdtemp(prefix="foundation-postgres-"))
        shutil.copy(PROJECT_ROOT / "compose.yaml", root)
        shutil.copytree(PROJECT_ROOT / "sql", root / "sql")
        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            port = available.getsockname()[1]
        database = {"name": "foundation_test", "user": "foundation_test_master", "port": port,
                    "startup_timeout": 240, "connect_timeout": 10, "statement_timeout": 30}
        password = secrets.token_urlsafe(32)
        secret_path = write_secret(password, root)
        env = compose_environment(database, secret_path)
        command = compose_command(root, project)
        try:
            start_postgres(database, secret_path, root, project)
            with connect(database, password) as connection:
                migrate(connection, root)
                value = "x" * 50000
                entry_id = insert_entry(connection, value)
                self.assertGreater(entry_id, 0)
                self.assertEqual(read_entry(connection, entry_id), (entry_id, value))
            # Stop/start reuses the exact same named volume, without deleting anything.
            run_command(command + ["stop", "postgres"], 30, env)
            start_postgres(database, secret_path, root, project)
            with connect(database, password) as connection:
                migrate(connection, root)
                self.assertEqual(read_entry(connection, entry_id), (entry_id, value))
                with connection.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM public.foundation_migrations")
                    self.assertEqual(cursor.fetchone()[0], 10)
                    cursor.execute("SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND tablename='test'")
                    self.assertEqual(cursor.fetchone()[0], 1)
                    cursor.execute("SELECT data_type, is_identity, identity_generation FROM information_schema.columns WHERE table_schema='public' AND table_name='test' AND column_name='id'")
                    self.assertEqual(cursor.fetchone(), ("bigint", "YES", "ALWAYS"))
            # Exercise the actual routers and PostgreSQL queries, never the normal database.
            import io
            import time
            import threading
            import httpx
            import uvicorn
            from fastapi.testclient import TestClient
            from app.api_credentials import PASSWORD_HASHER
            from app.auth import AuthService
            from app.api_users import APIUserStore
            from app.database import Database
            from app.logger import ApplicationLogger
            from app.main import create_app
            config = json.loads((PROJECT_ROOT / ".app.config.example").read_text())
            api_password = secrets.token_urlsafe(24)
            users = APIUserStore(Database(database, password))
            api_hash = PASSWORD_HASHER.hash(api_password)
            users.create("isolated_api_user", api_hash)
            signing_key = secrets.token_urlsafe(64)
            output = io.StringIO()
            logger = ApplicationLogger(config["logging"], root=root, stream=output)
            try:
                application = create_app(config, Database(database, password), AuthService(config["auth"], signing_key, users), logger)
                with TestClient(application) as client:
                    self.assertEqual(client.get("/health").status_code, 200)
                    token_response = client.post("/token", data={"username": "isolated_api_user", "password": api_password, "grant_type": "password", "scope": "test:read test:write", "client_id": "", "client_secret": ""})
                    self.assertEqual(token_response.status_code, 200)
                    access_token = token_response.json()["access_token"]
                    headers = {"Authorization": "Bearer " + access_token}
                    values = ["dragon", "DRAGON", "dragonfly", "red dragon", "a dragon b", "drXgon",
                              "100% pure", "literal_under", "", "  unchanged  ", "x" * 50000,
                              "'; DROP TABLE public.test; --"]
                    rows = []
                    for text in values:
                        response = client.post("/test", json={"value": text}, headers=headers)
                        self.assertEqual(response.status_code, 201, response.text)
                        self.assertEqual(response.json()["value"], text)
                        rows.append(response.json())
                    self.assertEqual(len({row["id"] for row in rows}), len(rows))
                    all_rows = client.get("/test", headers=headers).json()["items"]
                    self.assertEqual([row["id"] for row in all_rows], sorted(row["id"] for row in all_rows))
                    self.assertEqual(len(all_rows), len(rows) + 1)
                    for pattern, expected in (("dragon", ["dragon", "DRAGON"]),
                                              ("dragon%", ["dragon", "DRAGON", "dragonfly"]),
                                              ("%dragon", ["dragon", "DRAGON", "red dragon"]),
                                              ("%dragon%", ["dragon", "DRAGON", "dragonfly", "red dragon", "a dragon b"]),
                                              ("dr_gon", ["dragon", "DRAGON", "drXgon"]),
                                              (r"100\% pure", ["100% pure"]),
                                              (r"literal\_under", ["literal_under"]),
                                              ("", [""]), ("absent", []),
                                              ("'; DROP TABLE public.test; --", ["'; DROP TABLE public.test; --"])):
                        response = client.get("/test", params={"value": pattern}, headers=headers)
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual([row["value"] for row in response.json()["items"]], expected)
                    self.assertEqual(len(client.get("/test?value=%25dragon%25", headers=headers).json()["items"]), 5)
                    selected = rows[0]
                    for params in ({"id": selected["id"]}, {"id": selected["id"], "value": "%dragon%"}):
                        self.assertEqual(client.get("/test", params=params, headers=headers).json()["items"], [selected])
                    self.assertEqual(client.get("/test", params={"id": selected["id"], "value": "no match"}, headers=headers).json()["items"], [])
                    self.assertEqual(client.get("/test", params={"id": 9223372036854775807}, headers=headers).json()["items"], [])
                    response = client.get("/test", params={"value": "100% pure"}, headers=headers)
                    self.assertIn(response.headers["X-Interaction-ID"], output.getvalue())
                    for secret in (password, api_password, access_token, signing_key, api_hash):
                        self.assertNotIn(secret, output.getvalue())
                    # Replay the sanitized collection against the real isolated API.
                    import re
                    collection=json.loads((PROJECT_ROOT/"postman/Ouroboros.postman_collection.json").read_text(encoding="utf-8"))
                    variables={"base_url":"http://testserver","api_username":"isolated_api_user","api_password":api_password,"access_token":"","test_id":""}
                    def expand(value):
                        return re.sub(r"\{\{([^}]+)\}\}",lambda match:variables[match[1]],value)
                    for item in collection["item"][:8]:
                        spec=item["request"]
                        request_url=spec["url"]["raw"] if isinstance(spec["url"],dict) else spec["url"]
                        options={}
                        if isinstance(spec["url"],dict):
                            enabled={entry["key"]:expand(entry["value"]) for entry in spec["url"]["query"] if not entry.get("disabled",False)}
                            if enabled:options["params"]=enabled
                        if spec["auth"]["type"]=="bearer": options["headers"]={"Authorization":"Bearer "+variables["access_token"]}
                        body=spec.get("body",{})
                        if body.get("mode")=="urlencoded": options["data"]={entry["key"]:expand(entry["value"]) for entry in body["urlencoded"]}
                        if body.get("mode")=="raw": options["json"]=json.loads(body["raw"])
                        response=client.request(spec["method"],expand(request_url),**options)
                        expected=201 if spec["method"]=="POST" and "/test" in request_url else 401 if item==collection["item"][7] else 200
                        self.assertEqual(response.status_code,expected)
                        self.assertRegex(response.headers["X-Interaction-ID"],r"^[0-9]{24}$")
                        if request_url.endswith("/token"): variables["access_token"]=response.json()["access_token"]
                        if expected==201:
                            variables["test_id"]=str(response.json()["id"])
                            self.assertEqual(response.json()["value"],"Ouroboros est\u00e1 vivo! \U0001f40d\U0001f4bb")
                        if spec["method"]=="GET" and expected==200 and "/test" in request_url:
                            rows=response.json()["items"]
                            self.assertIsInstance(rows,list)
                            if "id=" in request_url:
                                self.assertEqual(len(rows),1)
                                self.assertEqual(str(rows[0]["id"]),variables["test_id"])
                            if "value=" in request_url:
                                self.assertTrue(rows)
                                self.assertTrue(all("ouroboros" in row["value"].lower() for row in rows))
                        if item==collection["item"][3]:
                            from itertools import product
                            for flags in product((False,True),repeat=2):
                                params={entry["key"]:expand(entry["value"]) for entry,enabled in zip(spec["url"]["query"],flags) if enabled}
                                filtered=client.get(expand(request_url),params=params,headers=options["headers"])
                                self.assertEqual(filtered.status_code,200)
                                entries=filtered.json()["items"]
                                self.assertIsInstance(entries,list)
                                self.assertTrue(entries)
                                if flags[0]:
                                    self.assertEqual(len(entries),1)
                                    self.assertEqual(str(entries[0]["id"]),variables["test_id"])
                                if flags[1]:
                                    self.assertTrue(all("ouroboros" in entry["value"].lower() for entry in entries))
                                    self.assertIn("value=%25Ouroboros%25",str(filtered.request.url))
                                    self.assertNotIn("%2525",str(filtered.request.url))
                                if not any(flags):self.assertEqual(entries,rows)
                            excluded=client.get(expand(request_url),params={"id":entry_id,"value":"%Ouroboros%"},headers=options["headers"])
                            self.assertEqual(excluded.status_code,200)
                            self.assertEqual(excluded.json()["items"],[])
                        if item==collection["item"][6]:
                            mixed=client.get("/test",params={"id":variables["test_id"],"value":"%oUrObOrOs%"},headers=options["headers"])
                            self.assertEqual(mixed.status_code,200)
                            self.assertEqual(mixed.json()["items"],rows)
                    run_command(command + ["stop", "postgres"], 30, env)
                    self.assertEqual(client.get("/health").status_code, 503)
                    self.assertEqual(client.get("/test", headers=headers).status_code, 503)
                    start_postgres(database, secret_path, root, project)
                    self.assertEqual(client.get("/health").status_code, 200)
                # Also verify the real ASGI server binds a socket and releases resources gracefully.
                provider = Database({**database,"max_connections":2}, password)
                auth = AuthService(config["auth"], signing_key, users)
                application = create_app(config, provider, auth, logger)
                @application.get("/concurrency/{index}")
                def concurrency_probe(index: int):
                    from app.logger import log_event
                    with provider.connection() as connection:
                        log_event("DEBUG","Concurrent operation entered",component="probe")
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT pg_sleep(%s)",(0.04,))
                        log_event("INFO","Concurrent operation completed",component="probe")
                    return {"index":index}
                with socket.socket() as available:
                    available.bind(("127.0.0.1", 0))
                    api_port = available.getsockname()[1]
                server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=api_port,
                                                       access_log=False, log_config=None))
                thread = threading.Thread(target=server.run, daemon=True)
                thread.start()
                try:
                    deadline = time.monotonic() + 10
                    while not server.started and thread.is_alive() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertTrue(server.started)
                    response = httpx.get(f"http://127.0.0.1:{api_port}/health", timeout=10)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("X-Interaction-ID", response.headers)
                    # A newly created API process/application must read data that
                    # was persisted before the previous client lifespan ended.
                    restarted_token = httpx.post(f"http://127.0.0.1:{api_port}/token", data={"username":"isolated_api_user", "password":api_password}, timeout=10)
                    self.assertEqual(restarted_token.status_code, 200)
                    restored = httpx.get(f"http://127.0.0.1:{api_port}/test", params={"id":entry_id},
                                        headers={"Authorization":"Bearer "+restarted_token.json()["access_token"]}, timeout=10)
                    self.assertEqual(restored.status_code, 200)
                    self.assertEqual([{key: row[key] for key in ('id','value')} for row in restored.json()["items"]], [{"id":entry_id,"value":value}])
                    import asyncio
                    async def overlapping():
                        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{api_port}",timeout=20) as http:
                            return await asyncio.gather(*(http.get(f"/concurrency/{index}") for index in range(12)))
                    overlapping_responses=asyncio.run(overlapping())
                    ids=[response.headers["X-Interaction-ID"] for response in overlapping_responses]
                    self.assertEqual(len(set(ids)),12)
                    for index,response in enumerate(overlapping_responses):
                        self.assertEqual(response.status_code,200)
                        lines=[line for line in output.getvalue().splitlines() if ids[index] in line]
                        self.assertTrue(any("Concurrent operation entered" in line for line in lines))
                        self.assertTrue(all(line.split(" | ")[4]==f"GET /concurrency/{index}" for line in lines))
                finally:
                    server.should_exit = True
                    thread.join(10)
                self.assertFalse(thread.is_alive())
                self.assertIsNone(provider.password)
                self.assertIsNone(auth.secret)
                with connect(database, password) as connection:
                    self.assertEqual(read_entry(connection, entry_id), (entry_id, value))
            finally:
                logger.close()
            with self.assertRaises(DatabaseError) as failure:
                connect(database, secrets.token_urlsafe(32))
            self.assertNotIn(password, str(failure.exception))
        finally:
            # The UUID project was created above, never selected from existing resources.
            # Only its disposable test volume is removed after persistence is verified.
            run_command(command + ["down", "--volumes"], 60, env)
            shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()

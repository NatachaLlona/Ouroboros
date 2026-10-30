"""Real account migration, multiple databases, and definitive port checks."""
import json
import os
import secrets
import shutil
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import uvicorn
from fastapi.testclient import TestClient
from psycopg import sql

from app.api_credentials import (PASSWORD_HASHER, configure_api_credentials,
                                 load_signing_secret, migrate_legacy_user)
from app.api_users import APIUserStore
from app.auth import AuthService
from app.config import PROJECT_ROOT, save_config
from app.credentials import write_secret
from app.database import (Database, DatabaseError, check_docker, compose_command,
                          compose_environment, connect, ensure_database, run_command, start_postgres)
from app.database_test import insert_entry, read_entry
from app.logger import ApplicationLogger
from app.main import create_app
from app.migrate import migrate


def available_port(preferred=0):
    if preferred == 0:
        from support_ports import approved_port
        return approved_port()
    with socket.socket() as channel:
        channel.bind(("127.0.0.1",preferred))
        return channel.getsockname()[1]


@unittest.skipUnless(os.environ.get("FOUNDATION_RUN_INTEGRATION")=="1", "Enable isolated Docker integration tests")
class AccountIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import uuid
        check_docker()
        cls.project="foundation-accounts-"+uuid.uuid4().hex
        cls.root=Path(tempfile.mkdtemp(prefix="foundation-accounts-"))
        shutil.copy(PROJECT_ROOT/"compose.yaml",cls.root)
        shutil.copytree(PROJECT_ROOT/"sql",cls.root/"sql")
        cls.config=json.loads((PROJECT_ROOT/".app.config.example").read_text())
        port=available_port()
        cls.database={**cls.config["database"],"name":"original_database","user":"isolated_master","port":port,"startup_timeout":240}
        cls.config["database"]=cls.database
        cls.password=secrets.token_urlsafe(32)
        cls.secret=write_secret(cls.password,cls.root)
        cls.env=compose_environment(cls.database,cls.secret)
        cls.command=compose_command(cls.root,cls.project)
        def cleanup():
            run_command(cls.command+["down","--volumes"],60,cls.env)
            shutil.rmtree(cls.root)
        cls.addClassCleanup(cleanup)
        start_postgres(cls.database,cls.secret,cls.root,cls.project)
        ensure_database(cls.database,cls.password)
        with connect(cls.database,cls.password) as connection:
            migrate(connection,cls.root)
        cls.users=APIUserStore(Database(cls.database,cls.password))
        cls.first_password=secrets.token_urlsafe(24)
        cls.first_hash=PASSWORD_HASHER.hash(cls.first_password)
        cls.signing_key=load_signing_secret(cls.root)

    def application(self):
        provider=Database(self.database,self.password)
        users=APIUserStore(provider)
        auth=AuthService(self.config["auth"],self.signing_key,users)
        import io
        self.output=io.StringIO()
        self.logger=ApplicationLogger(self.config["logging"],root=self.root,stream=self.output)
        self.addCleanup(self.logger.close)
        return create_app(self.config,provider,auth,self.logger)

    def test_01_migration_users_scopes_and_multiple_databases(self):
        self.config["auth"].update(username="legacy_api_user",password_hash=self.first_hash)
        (self.root/".app.config").write_text(json.dumps(self.config))
        with connect(self.database,self.password) as connection:
            entry_id=insert_entry(connection,"preserved before account migration")
        migrate_legacy_user(self.config,self.users,self.root)
        first=self.users.get_by_username("legacy_api_user")
        self.assertTrue(first.password_hash==self.first_hash)
        self.assertEqual(self.users.count(),1)
        # Repeat the old import after a simulated crash between commit and config cleanup.
        self.config["auth"].update(username="legacy_api_user",password_hash=self.first_hash)
        migrate_legacy_user(self.config,self.users,self.root)
        self.assertEqual(self.users.count(),1)
        self.assertEqual(self.users.get_by_username("legacy_api_user").id,first.id)
        text=(self.root/".app.config").read_text()
        self.assertNotIn("password_hash",text)
        self.assertNotIn(self.first_hash,text)
        self.assertEqual(set(self.config["api_users"]),{"last_api_username"})
        second_password=secrets.token_urlsafe(24)
        with patch("builtins.input",side_effect=["create","second_api_user"]), patch("app.api_credentials.read_password",return_value=second_password):
            configure_api_credentials(self.config,self.users,self.root)
        self.assertEqual(self.users.count(),2)
        with patch("builtins.input",return_value="y"), patch("app.api_credentials.read_password") as prompt:
            configure_api_credentials(self.config,self.users,self.root)
            prompt.assert_not_called()
        with TestClient(self.application()) as client:
            tokens=[]
            for username,password in (("legacy_api_user",self.first_password),("second_api_user",second_password)):
                response=client.post("/token",data={"username":username,"password":password})
                self.assertEqual(response.status_code,200)
                token=response.json()["access_token"]
                payload=client.app.state.auth.decode(token)
                tokens.append((token,payload))
            self.assertNotEqual(tokens[0][1]["sub"],tokens[1][1]["sub"])
            self.assertEqual(tokens[0][1]["sub"],str(first.id))
            self.assertEqual(client.post("/token",data={"username":"legacy_api_user","password":"invalid"}).status_code,401)
            second=self.users.get_by_username("second_api_user")
            self.users.change_role(second.id, first.id, "administrator")
            self.users.change_role(first.id, second.id, "standard")
            with connect(self.database,self.password) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE public.api_users SET scopes=%s WHERE id=%s",(["test:read"],second.id))
            self.assertEqual(client.post("/token",data={"username":"second_api_user","password":second_password,"scope":"test:write"}).status_code,403)
            read_token=client.post("/token",data={"username":"second_api_user","password":second_password}).json()["access_token"]
            self.assertEqual(client.post("/test",json={"value":"not inserted"},headers={"Authorization":"Bearer "+read_token}).status_code,403)
            # Existing tokens cannot retain permissions removed in the database.
            self.assertEqual(client.post("/test",json={"value":"not inserted"},headers={"Authorization":"Bearer "+tokens[1][0]}).status_code,403)
            with connect(self.database,self.password) as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE public.api_users SET is_active=FALSE WHERE id=%s",(second.id,))
            self.assertEqual(client.post("/token",data={"username":"second_api_user","password":second_password}).status_code,401)
            self.assertEqual(client.get("/test",headers={"Authorization":"Bearer "+read_token}).status_code,401)
            for sensitive in (self.password,self.first_hash,self.first_password,second_password,read_token):
                self.assertNotIn(sensitive,self.output.getvalue())
        # A conflicting legacy import must not overwrite password or privileges.
        original=self.users.get_by_id(first.id)
        conflict={**self.config,"auth":{**self.config["auth"],"username":original.username,"password_hash":PASSWORD_HASHER.hash("conflicting-test-password")}}
        (self.root/".app.config").write_text(json.dumps(conflict))
        before=(self.root/".app.config").read_bytes()
        with self.assertRaises(DatabaseError):migrate_legacy_user(conflict,self.users,self.root)
        self.assertTrue((self.root/".app.config").read_bytes()==before)
        self.assertTrue(self.users.get_by_id(first.id).password_hash==self.first_hash)
        save_config(self.config,self.root)
        other={**self.database,"name":"another_database"}
        # Container initialization values are not used to provision the new database.
        start_postgres(other,self.secret,self.root,self.project)
        ensure_database(other,self.password)
        with connect(other,self.password) as connection:
            migrate(connection,self.root)
        other_users=APIUserStore(Database(other,self.password))
        self.assertEqual(other_users.count(),0)
        with connect(self.database,self.password) as connection:
            self.assertEqual(read_entry(connection,entry_id),(entry_id,"preserved before account migration"))
        # No CREATEDB privilege: fail clearly without removing either existing database.
        limited_password=secrets.token_urlsafe(24)
        with connect(self.database,self.password) as connection, connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE ROLE limited_master LOGIN NOCREATEDB NOSUPERUSER PASSWORD {}").format(sql.Literal(limited_password)))
        with self.assertRaisesRegex(DatabaseError,"permission to create"):
            ensure_database({**self.database,"name":"not_permitted","user":"limited_master"},limited_password)
        with connect(self.database,self.password) as connection:
            self.assertIsNotNone(read_entry(connection,entry_id))
        self.assertNotIn("password_hash",(self.root/".app.config").read_text())

    def test_02_definitive_ports_and_swagger(self):
        if self.database["port"]!=6669:
            self.skipTest("Port 6669 is occupied; isolated account checks used a temporary port")
        try:available_port(6969)
        except OSError:self.skipTest("Port 6969 is occupied; existing service was not stopped")
        app=self.application()
        server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=6969,access_log=False,log_config=None))
        thread=threading.Thread(target=server.run,daemon=True)
        thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(0.05)
            self.assertTrue(server.started)
            self.assertEqual(httpx.get("http://127.0.0.1:6969/health").status_code,200)
            self.assertEqual(httpx.get("http://127.0.0.1:6969/docs").status_code,200)
        finally:
            server.should_exit=True
            thread.join(10)
        self.assertFalse(thread.is_alive())


    def test_03_derived_project_has_its_own_volume_and_accounts(self):
        from app.infrastructure import require_infrastructure
        root=Path(tempfile.mkdtemp(prefix="foundation-derived-"))
        shutil.copy(PROJECT_ROOT/"compose.yaml",root)
        shutil.copytree(PROJECT_ROOT/"sql",root/"sql")
        project=self.project+"-derived"
        config=json.loads((PROJECT_ROOT/".app.config.example").read_text())
        config["infrastructure"]["project_name"]=project
        self.assertEqual(require_infrastructure(config,root),project)
        from support_ports import approved_port
        database={**self.database,"port":approved_port('derived')}
        password=secrets.token_urlsafe(32)
        secret=write_secret(password,root)
        environment=compose_environment(database,secret)
        command=compose_command(root,project)
        before=self.users.count()
        try:
            start_postgres(database,secret,root,project)
            ensure_database(database,password)
            with connect(database,password) as connection:
                migrate(connection,root)
            users=APIUserStore(Database(database,password))
            self.assertEqual(users.count(),0)
            users.create("derived_only",PASSWORD_HASHER.hash(secrets.token_urlsafe(24)))
            self.assertEqual(self.users.count(),before)
            self.assertIsNone(self.users.get_by_username("derived_only"))
            result=run_command(command+["ps","--quiet","postgres"],15,environment)
            container=json.loads(run_command(["docker","inspect",result.stdout.decode().strip()],15,environment).stdout)[0]
            volumes={mount["Name"] for mount in container["Mounts"] if mount["Type"]=="volume"}
            self.assertEqual(volumes,{project+"_postgres_data"})
            self.assertNotIn(self.project+"_postgres_data",volumes)
        finally:
            run_command(command+["down","--volumes"],60,environment)
            shutil.rmtree(root)


    def test_04_real_startup_coordinator_reuses_owned_resources(self):
        from start import main
        config=json.loads(json.dumps(self.config))
        config["infrastructure"]={"project_name":self.project,"workspace":str(self.root)}
        save_config(config,self.root)
        observed=[]
        def server(application,settings):
            observed.append(application)
            schema=application.openapi()
            self.assertEqual(schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]["tokenUrl"],"/token")
        with patch("start.prompt_credentials",return_value=self.password), patch("builtins.input",return_value="y"), patch("start.run_api",side_effect=server):
            self.assertEqual(main(self.root),0)
        self.assertEqual(len(observed),1)
        self.assertIsNone(observed[0].state.database.password)
        self.assertIsNone(observed[0].state.auth.secret)
        self.assertEqual(self.users.count(),2)

    def test_05_role_migration_recovery_and_restart(self):
        """Upgrade a populated v2 schema without changing identities or hashes."""
        database = {**self.database, "name": "role_migration_database"}
        ensure_database(database, self.password)
        with tempfile.TemporaryDirectory() as directory:
            legacy_root = Path(directory)
            (legacy_root/"sql/migrations").mkdir(parents=True)
            for name in ("001_create_test.sql", "002_create_api_users.sql"):
                shutil.copy(PROJECT_ROOT/"sql/migrations"/name, legacy_root/"sql/migrations")
            # The old runner expects the old shape; create and checksum the old
            # schema explicitly so the current runner executes only migration 003.
            import hashlib
            with connect(database, self.password) as connection, connection.cursor() as cursor:
                cursor.execute("CREATE TABLE public.foundation_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)")
                for file in sorted((legacy_root/"sql/migrations").glob("*.sql")):
                    content = file.read_bytes()
                    cursor.execute(content.decode("utf-8"))
                    cursor.execute("INSERT INTO public.foundation_migrations(version,checksum) VALUES (%s,%s)", (file.name, hashlib.sha256(content).hexdigest()))
                cursor.execute("INSERT INTO public.api_users(username,password_hash,scopes) VALUES (%s,%s,%s) RETURNING id", ("explicit_selection", self.first_hash, ["test:read", "test:write"]))
                old_id = cursor.fetchone()[0]
                preserved_id = insert_entry(connection, "role migration preserves records")
            with connect(database, self.password) as connection:
                migrate(connection, self.root)
            users = APIUserStore(Database(database, self.password))
            self.assertFalse(users.has_administrator())
            user = users.get_by_id(old_id)
            self.assertEqual(user.role, "standard")
            self.assertEqual(user.password_hash, self.first_hash)
            config = json.loads(json.dumps(self.config))
            with patch("builtins.input", side_effect=["promote", "explicit_selection"]), patch("app.api_credentials.read_password") as password_prompt:
                configure_api_credentials(config, users, legacy_root)
                password_prompt.assert_not_called()
            self.assertTrue(users.has_administrator())
            with patch("builtins.input") as selection, patch("app.api_credentials.read_password") as password_prompt:
                configure_api_credentials(config, users, legacy_root)
                selection.assert_not_called()
                password_prompt.assert_not_called()
            run_command(self.command+["stop", "postgres"], 30, self.env)
            start_postgres(self.database, self.secret, self.root, self.project)
            with connect(database, self.password) as connection:
                migrate(connection, self.root)
                self.assertEqual(read_entry(connection, preserved_id), (preserved_id, "role migration preserves records"))
            recovered = users.get_by_id(old_id)
            self.assertEqual((recovered.id, recovered.password_hash, recovered.role), (old_id, self.first_hash, "administrator"))
            self.assertEqual(users.count(), 1)

    def test_06_roles_pagination_concurrency_and_collection(self):
        """Exercise public contracts and competing demotions on real PostgreSQL."""
        from concurrent.futures import ThreadPoolExecutor
        from app.api_users import UserManagementError
        from app.database_test import page_entries
        import io

        database = {**self.database, "name": "administration_database"}
        ensure_database(database, self.password)
        with connect(database, self.password) as connection:
            migrate(connection, self.root)
        provider = Database(database, self.password)
        users = APIUserStore(provider)
        config = json.loads(json.dumps(self.config))
        with tempfile.TemporaryDirectory() as directory:
            with patch("builtins.input", return_value="first_admin"), patch("app.api_credentials.read_password", return_value=self.first_password):
                configure_api_credentials(config, users, Path(directory))
        admin = users.get_by_username("first_admin")
        self.assertEqual(admin.role, "administrator")
        output = io.StringIO()
        logger = ApplicationLogger(self.config["logging"], root=self.root, stream=output)
        self.addCleanup(logger.close)
        auth = AuthService(self.config["auth"], self.signing_key, users)
        passwords = [self.first_password]
        tokens = []
        with TestClient(create_app(config, provider, auth, logger)) as client:
            def login(username, password):
                response = client.post("/token", data={"username": username, "password": password})
                self.assertEqual(response.status_code, 200)
                token = response.json()["access_token"]
                tokens.append(token)
                return {"Authorization": "Bearer "+token}
            administrator = login(admin.username, self.first_password)
            self.assertEqual(client.post("/token", data={"username": self.database["user"], "password": self.password}).status_code, 401)
            created = []
            for name, role in (("ordinary", "standard"), ("second_admin", "administrator")):
                password = secrets.token_urlsafe(24)
                passwords.append(password)
                response = client.post("/users", json={"username": name, "password": password, "role": role}, headers=administrator)
                self.assertEqual(response.status_code, 201, response.text)
                user = response.json()
                self.assertEqual(set(user), {"id", "username", "role", "is_active", "created_at"})
                self.assertEqual(user["role"], role)
                created.append((user, login(name, password)))
            standard, standard_headers = created[0]
            second, second_headers = created[1]
            self.assertEqual(client.get("/users", headers=standard_headers).status_code, 403)
            self.assertEqual(client.post("/users", json={"username": "blocked", "password": "not-persisted-password"}, headers=standard_headers).status_code, 403)
            self.assertEqual(client.put(f'/users/{standard["id"]}/role', json={"role": "administrator"}, headers=standard_headers).status_code, 403)
            self.assertEqual(client.post("/users", json={"username": "ordinary", "password": "not-persisted-password"}, headers=administrator).status_code, 409)
            self.assertEqual(client.put("/users/9223372036854775807/role", json={"role": "standard"}, headers=administrator).status_code, 404)
            # The same token must immediately lose administration after demotion.
            self.assertEqual(client.put(f'/users/{second["id"]}/role', json={"role": "standard"}, headers=administrator).status_code, 200)
            self.assertEqual(client.get("/users", headers=second_headers).status_code, 403)
            with self.assertRaises(UserManagementError) as revoked:
                users.create_managed(second["id"], "revoked_actor_write", self.first_hash, "standard")
            self.assertEqual(revoked.exception.status, 403)
            self.assertEqual(client.put(f"/users/{admin.id}/role", json={"role": "standard"}, headers=administrator).status_code, 409)
            self.assertEqual(client.put(f'/users/{second["id"]}/role', json={"role": "administrator"}, headers=administrator).status_code, 200)
            audit = [line for line in output.getvalue().splitlines() if "API user role changed" in line]
            self.assertTrue(audit)
            for line in audit:
                self.assertIn('"administrator_id": '+str(admin.id), line)
                self.assertIn('"user_id": '+str(second["id"]), line)
                self.assertIn('"previous_role":', line)
                self.assertIn('"new_role":', line)
                self.assertRegex(line.split(" | ")[1], r"^\d{24}$")
            for index in range(35):
                response = client.post("/test", json={"value": f"page-marker-{index:02d}"}, headers=standard_headers)
                self.assertEqual(response.status_code, 201)
            for index in range(12):
                users.create("pagination_user_"+str(index), self.first_hash)
            for path in ("/test", "/users"):
                first = client.get(path, headers=administrator).json()
                self.assertEqual((first["page"], first["page_size"]), (1, 50))
                self.assertEqual(first["count"], len(first["items"]))
                empty = client.get(path, params={"page": 999, "page_size": 10}, headers=administrator).json()
                self.assertEqual(empty["count"], first["count"])
                self.assertEqual(empty["items"], [])
                for params in ({"page": 0}, {"page_size": 9}, {"page_size": 51}, {"page": "1.5"}):
                    self.assertEqual(client.get(path, params=params, headers=administrator).status_code, 422)
            user_page = client.get("/users?page=2&page_size=10", headers=administrator).json()
            self.assertEqual(user_page["count"], 15)
            self.assertEqual(len(user_page["items"]), 5)
            first = client.get("/test", params={"value": "%PAGE-MARKER%", "page_size": 10}, headers=standard_headers).json()
            next_page = client.get("/test", params={"value": "%page-marker%", "page_size": 10, "page": 2}, headers=standard_headers).json()
            self.assertEqual((first["count"], len(first["items"])), (35, 10))
            self.assertEqual(next_page["count"], 35)
            self.assertLess(first["items"][-1]["id"], next_page["items"][0]["id"])
            selected = first["items"][0]
            exact = client.get("/test", params={"id": selected["id"], "value": "%page-marker%"}, headers=standard_headers).json()
            self.assertEqual((exact["count"], exact["items"]), (1, [selected]))
            self.assertEqual(client.get("/test?value=absent", headers=standard_headers).json()["count"], 0)
            # Concurrent commits cannot split count and page into different snapshots.
            def writer():
                for index in range(5):
                    with users.database.connection() as connection:
                        insert_entry(connection, "page-marker-concurrent")
            with ThreadPoolExecutor(max_workers=1) as pool:
                task = pool.submit(writer)
                for _ in range(12):
                    with users.database.connection() as connection:
                        result = page_entries(connection, value="%page-marker%")
                    self.assertEqual(result["count"], len(result["items"]))
                task.result()
            # Replay every administrative request definition without pretending to
            # execute Postman's JavaScript sandbox.
            import re
            collection = json.loads((PROJECT_ROOT/"postman/Ouroboros.postman_collection.json").read_text(encoding="utf-8"))
            variables = {"base_url": "http://testserver", "admin_username": admin.username, "admin_password": self.first_password,
                         "standard_username": "collection_standard", "standard_password": secrets.token_urlsafe(24),
                         "additional_admin_username": "collection_admin", "additional_admin_password": secrets.token_urlsafe(24)}
            def expand(value):
                return re.sub(r"\{\{([^}]+)\}\}", lambda match: variables[match[1]], value)
            for item in collection["item"][8]["item"]:
                spec = item["request"]
                url = expand(spec["url"]["raw"] if isinstance(spec["url"], dict) else spec["url"])
                options = {}
                if spec["auth"]["type"] == "bearer":
                    options["headers"] = {"Authorization": "Bearer "+expand(spec["auth"]["bearer"][0]["value"])}
                body = spec.get("body", {})
                if body.get("mode") == "raw": options["json"] = json.loads(expand(body["raw"]))
                if body.get("mode") == "urlencoded": options["data"] = {entry["key"]: expand(entry["value"]) for entry in body["urlencoded"]}
                response = client.request(spec["method"], url, **options)
                expected = int(re.search(r"status\((\d+)\)", item["event"][0]["script"]["exec"][0])[1])
                self.assertEqual(response.status_code, expected, item["name"])
                if "/token" in url:
                    who = "standard" if "standard" in item["name"].lower() else "admin"
                    variables[who+"_token"] = response.json()["access_token"]
                    tokens.append(response.json()["access_token"])
                if item["name"].startswith("10"):
                    variables["standard_user_id"] = str(response.json()["id"])
                if item["name"].startswith("16"):
                    variables["additional_admin_id"] = str(response.json()["id"])
            passwords.extend((variables["standard_password"], variables["additional_admin_password"]))
            # Restore the additional admin to standard, leaving exactly two active
            # administrators before simultaneous self-demotions.
            barrier = threading.Barrier(2)
            def demote(user_id):
                barrier.wait(timeout=10)
                try:
                    users.change_role(user_id, user_id, "standard")
                    return 200
                except UserManagementError as error:
                    return error.status
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(demote, (admin.id, second["id"])))
            self.assertEqual(sorted(results), [200, 409])
            with users.database.connection() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM public.api_users WHERE role='administrator' AND is_active")
                self.assertEqual(cursor.fetchone()[0], 1)
                cursor.execute("SELECT password_hash FROM public.api_users")
                hashes = [row[0] for row in cursor.fetchall()]
            for secret in passwords+tokens+hashes+[self.password, self.signing_key]:
                self.assertNotIn(secret, output.getvalue())

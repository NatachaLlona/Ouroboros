"""Ordered QA role lifecycle with real accounts, tokens and disposable storage."""
import io
import json
import os
import secrets
import shutil
import socket
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api_credentials import configure_api_credentials
from app.api_users import APIUserStore, UserManagementError
from app.auth import AuthService
from app.config import PROJECT_ROOT
from app.credentials import write_secret
from app.database import Database, check_docker, compose_command, compose_environment, connect, run_command, start_postgres
from app.logger import ApplicationLogger
from app.main import create_app
from app.migrate import migrate


@unittest.skipUnless(os.environ.get("FOUNDATION_RUN_INTEGRATION") == "1", "QA lifecycle requires isolated Docker integration")
class QARoleLifecycleTests(unittest.TestCase):
    """Share only run-owned resources; later phases block after a failed phase."""

    @classmethod
    def setUpClass(cls):
        check_docker()
        cls.root = Path(tempfile.mkdtemp(prefix="foundation-qa-"))
        cls.project = "foundation-qa-"+uuid.uuid4().hex
        cls.config = json.loads((PROJECT_ROOT/".app.config.example").read_text())
        shutil.copy(PROJECT_ROOT/"compose.yaml", cls.root)
        shutil.copytree(PROJECT_ROOT/"sql", cls.root/"sql")
        from support_ports import approved_port
        port = approved_port('database')
        cls.database_config = {**cls.config["database"], "name": "qa_lifecycle", "user": "qa_master", "port": port, "startup_timeout": 240}
        cls.master_password = secrets.token_urlsafe(32)
        cls.secret = write_secret(cls.master_password, cls.root)
        cls.command = compose_command(cls.root, cls.project)
        cls.environment = compose_environment(cls.database_config, cls.secret)
        def cleanup():
            # This exact random project/root was allocated above, never read
            # from normal configuration or discovered by a name prefix.
            try:
                run_command(cls.command+["down", "--volumes"], 60, cls.environment)
            finally:
                shutil.rmtree(cls.root)
        cls.addClassCleanup(cleanup)
        start_postgres(cls.database_config, cls.secret, cls.root, cls.project)
        with connect(cls.database_config, cls.master_password) as connection:
            migrate(connection, cls.root)
        cls.provider = Database(cls.database_config, cls.master_password)
        cls.users = APIUserStore(cls.provider)
        cls.admin_password = secrets.token_urlsafe(24)
        cls.standard_password = secrets.token_urlsafe(24)
        cls.output = io.StringIO()
        cls.logger = ApplicationLogger(cls.config["logging"], root=cls.root, stream=cls.output)
        cls.addClassCleanup(cls.logger.close)
        cls.auth = AuthService(cls.config["auth"], secrets.token_urlsafe(64), cls.users)
        cls.client = TestClient(create_app(cls.config, cls.provider, cls.auth, cls.logger))
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)
        cls.phase = 0

    def setUp(self):
        from support_log_evidence import assert_response_logs
        callback = lambda response: assert_response_logs(self,response,self.output.getvalue,self.logger)
        self.client.event_hooks["response"].append(callback)
        self.addCleanup(lambda:self.client.event_hooks["response"].remove(callback))

    def require_phase(self, phase):
        """Skip downstream actions after a failed prerequisite, classified BLOCKED."""
        if type(self).phase != phase:
            self.skipTest("BLOCKED: previous QA lifecycle phase did not complete")

    def login(self, username, password):
        response = self.client.post("/token", data={"username": username, "password": password})
        self.assertEqual(response.status_code, 200)
        return {"Authorization": "Bearer "+response.json()["access_token"]}

    def admin_access(self, headers):
        self.assertEqual(self.client.get("/users", headers=headers).status_code, 200)
        # Exercise administrative writes, not only a list permission check.
        response = self.client.post("/users", headers=headers,
                                    json={"username": "probe_"+uuid.uuid4().hex, "password": secrets.token_urlsafe(24)})
        self.assertEqual(response.status_code, 201)
        target = response.json()["id"]
        self.assertEqual(self.client.put(f"/users/{target}/role", headers=headers, json={"role": "standard"}).status_code, 200)

    def standard_access(self, headers):
        self.assertEqual(self.client.get("/test", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/test", headers=headers, json={"value": "QA role lifecycle"}).status_code, 201)
        self.assertEqual(self.client.get("/users", headers=headers).status_code, 403)
        self.assertEqual(self.client.post("/users", headers=headers, json={"username": "blocked", "password": "not-persisted"}).status_code, 403)
        self.assertEqual(self.client.put(f"/users/{type(self).standard_id}/role", headers=headers, json={"role": "administrator"}).status_code, 403)

    def test_01_first_administrator(self):
        self.require_phase(0)
        with patch("builtins.input", return_value="qa_administrator"), patch("app.api_credentials.read_password", return_value=self.admin_password):
            configure_api_credentials(self.config, self.users, self.root)
        administrator = self.users.get_by_username("qa_administrator")
        self.assertEqual(administrator.role, "administrator")
        type(self).admin_id = administrator.id
        type(self).phase = 1

    def test_02_administrator_access(self):
        self.require_phase(1)
        headers = self.login("qa_administrator", self.admin_password)
        type(self).admin_headers = headers
        self.admin_access(headers)
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/test", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/test", headers=headers, json={"value": "first administrator"}).status_code, 201)
        type(self).phase = 2

    def test_03_default_standard_creation(self):
        self.require_phase(2)
        response = self.client.post("/users", headers=self.admin_headers, json={"username": "qa_standard", "password": self.standard_password})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["role"], "standard")
        type(self).standard_id = response.json()["id"]
        type(self).phase = 3

    def test_04_standard_permissions(self):
        self.require_phase(3)
        headers = self.login("qa_standard", self.standard_password)
        type(self).old_standard_headers = headers
        self.standard_access(headers)
        type(self).phase = 4

    def test_05_promotion_existing_token(self):
        self.require_phase(4)
        response = self.client.put(f"/users/{self.standard_id}/role", headers=self.admin_headers, json={"role": "administrator"})
        self.assertEqual(response.status_code, 200)
        self.admin_access(self.old_standard_headers)
        type(self).phase = 5

    def test_06_promotion_new_token(self):
        self.require_phase(5)
        headers = self.login("qa_standard", self.standard_password)
        type(self).promoted_headers = headers
        self.admin_access(headers)
        type(self).phase = 6

    def test_07_demotion_existing_tokens(self):
        self.require_phase(6)
        response = self.client.put(f"/users/{self.standard_id}/role", headers=self.admin_headers, json={"role": "standard"})
        self.assertEqual(response.status_code, 200)
        self.standard_access(self.promoted_headers)
        self.standard_access(self.old_standard_headers)
        type(self).phase = 7

    def test_08_last_administrator(self):
        self.require_phase(7)
        response = self.client.put(f"/users/{self.admin_id}/role", headers=self.admin_headers, json={"role": "standard"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.users.get_by_id(self.admin_id).role, "administrator")
        type(self).phase = 8

    def test_09_concurrent_demotions(self):
        self.require_phase(8)
        self.users.change_role(self.admin_id, self.standard_id, "administrator")
        barrier = threading.Barrier(2)
        def demote(user_id):
            barrier.wait(timeout=10)
            try:
                self.users.change_role(user_id, user_id, "standard")
                return 200
            except UserManagementError as error:
                return error.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(demote, (self.admin_id, self.standard_id)))
        self.assertEqual(sorted(results), [200, 409])
        current = [self.users.get_by_id(user_id) for user_id in (self.admin_id, self.standard_id)]
        self.assertEqual(sum(user.role == "administrator" and user.is_active for user in current), 1)
        type(self).phase = 9

    def test_10_collection_lifecycle_http_replay(self):
        """Replay canonical lifecycle HTTP definitions without a Postman sandbox."""
        self.require_phase(9)
        import re
        active = next(self.users.get_by_id(user_id) for user_id in (self.admin_id, self.standard_id)
                      if self.users.get_by_id(user_id).role == "administrator")
        password = self.admin_password if active.id == self.admin_id else self.standard_password
        admin_headers = self.login(active.username, password)
        standard_name = "collection_"+uuid.uuid4().hex
        standard_password = secrets.token_urlsafe(24)
        response = self.client.post("/users", headers=admin_headers, json={"username": standard_name, "password": standard_password})
        self.assertEqual(response.status_code, 201)
        standard_headers = self.login(standard_name, standard_password)
        variables = {"base_url": "http://testserver", "admin_username": active.username,
                     "admin_token": admin_headers["Authorization"].split(" ",1)[1],
                     "standard_username": standard_name, "standard_password": standard_password,
                     "standard_user_id": str(response.json()["id"]),
                     "standard_token": standard_headers["Authorization"].split(" ",1)[1],
                     "lifecycle_probe_password": secrets.token_urlsafe(24)}
        collection = json.loads((PROJECT_ROOT/"postman/Ouroboros.postman_collection.json").read_text(encoding="utf-8"))
        def expand(value):
            return re.sub(r"\{\{([^}]+)\}\}", lambda match: variables[match[1]], value)
        for item in collection["item"][9]["item"]:
            spec = item["request"]
            number = int(item["name"][:2])
            if any(event["listen"] == "prerequest" for event in item["event"]):
                variables["lifecycle_probe_username"] = "probe_"+uuid.uuid4().hex
            options = {}
            if spec["auth"]["type"] == "bearer":
                options["headers"] = {"Authorization": "Bearer "+expand(spec["auth"]["bearer"][0]["value"])}
            body = spec.get("body", {})
            if body.get("mode") == "raw": options["json"] = json.loads(expand(body["raw"]))
            if body.get("mode") == "urlencoded": options["data"] = {field["key"]: expand(field["value"]) for field in body["urlencoded"]}
            response = self.client.request(spec["method"], expand(spec["url"]["raw"] if isinstance(spec["url"], dict) else spec["url"]), **options)
            script = next(event["script"]["exec"] for event in item["event"] if event["listen"] == "test")
            expected = int(re.search(r"status\((\d+)\)", script[0])[1])
            self.assertEqual(response.status_code, expected, item["name"])
            if number == 21:
                found = next(user for user in response.json()["items"] if user["username"] == active.username)
                variables["admin_user_id"] = str(found["id"])
            if number == 22: variables["old_standard_token"] = variables["standard_token"]
            if number == 27: variables["promoted_token"] = response.json()["access_token"]
            if number in (25,29): variables["lifecycle_probe_id"] = str(response.json()["id"])
            if spec["method"] == "GET" and expected == 200:
                self.assertIsInstance(response.json()["items"], list)

    def exercise_password_change(self, role):
        """Check self-service, revocation and secret-free logs for either profile."""
        from app.api_credentials import PASSWORD_HASHER
        password, new_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)+"🐍💻"
        user = self.users.create("password_"+uuid.uuid4().hex, PASSWORD_HASHER.hash(password), role=role)
        peer_password = secrets.token_urlsafe(24)
        peer = self.users.create("peer_"+uuid.uuid4().hex, PASSWORD_HASHER.hash(peer_password))
        headers = self.login(user.username,password)
        other_token = self.login(user.username,password)
        peer_headers = self.login(peer.username,peer_password)
        key = self.auth.secret
        before = self.users.get_by_id(user.id)
        for body in ({"current_password":"wrong","new_password":new_password},
                     {"current_password":password,"new_password":password}):
            response = self.client.put("/users/me/password",headers=headers,json=body)
            self.assertEqual(response.status_code,400)
            self.assertEqual(self.users.get_by_id(user.id).credential_version,before.credential_version)
        for body in ({}, {"current_password":password}, {"current_password":123,"new_password":new_password},
                     {"current_password":password,"new_password":""},
                     {"current_password":password,"new_password":new_password,"id":peer.id}):
            self.assertEqual(self.client.put("/users/me/password",headers=headers,json=body).status_code,422)
        response = self.client.put("/users/me/password",headers=headers,json={"current_password":password,"new_password":new_password})
        self.assertEqual(response.status_code,204)
        self.assertEqual(response.content,b"")
        changed = self.users.get_by_id(user.id)
        self.assertEqual(changed.credential_version,before.credential_version+1)
        self.assertEqual(changed.role,role)
        self.assertTrue(PASSWORD_HASHER.verify(changed.password_hash,new_password))
        for old in (headers,other_token):
            self.assertEqual(self.client.get("/test",headers=old).status_code,401)
            self.assertEqual(self.client.put("/users/me/password",headers=old,json={"current_password":new_password,"new_password":password}).status_code,401)
        self.assertEqual(self.client.post("/token",data={"username":user.username,"password":password}).status_code,401)
        fresh = self.login(user.username,new_password)
        self.assertEqual(self.client.get("/test",headers=fresh).status_code,200)
        self.assertEqual(self.client.get("/test",headers=peer_headers).status_code,200)
        self.assertEqual(self.auth.secret,key)
        output = self.output.getvalue()
        request_lines = [line for line in output.splitlines() if response.headers["X-Interaction-ID"] in line]
        self.assertTrue(any("API password changed" in line and '"user_id": '+str(user.id) in line for line in request_lines))
        password_lines = [line for line in output.splitlines() if "PUT /users/me/password" in line]
        self.assertFalse(any("Request JSON body received" in line for line in password_lines))
        for value in (password,new_password,before.password_hash,changed.password_hash,headers["Authorization"].split(" ",1)[1]):
            self.assertNotIn(value,output)

    def test_11_standard_password_change(self):
        self.exercise_password_change("standard")

    def test_12_administrator_password_change(self):
        self.exercise_password_change("administrator")

    def test_13_concurrent_password_changes(self):
        from app.api_credentials import PASSWORD_HASHER
        original = secrets.token_urlsafe(24)
        user = self.users.create("race_"+uuid.uuid4().hex,PASSWORD_HASHER.hash(original))
        headers = self.login(user.username,original)
        candidates = [secrets.token_urlsafe(24),secrets.token_urlsafe(24)]
        barrier = threading.Barrier(2)
        def change(value):
            barrier.wait(timeout=10)
            return self.client.put("/users/me/password",headers=headers,json={"current_password":original,"new_password":value}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool: statuses = list(pool.map(change,candidates))
        self.assertEqual(sorted(statuses),[204,401])
        self.assertEqual(self.users.get_by_id(user.id).credential_version,2)
        for password,status in zip(candidates,statuses):
            self.assertEqual(self.client.post("/token",data={"username":user.username,"password":password}).status_code,200 if status == 204 else 401)

    def test_15_administrator_password_reset(self):
        """Exercise real transactions, revocation, audit and locked authorization."""
        from app.api_credentials import PASSWORD_HASHER
        for level in ("INFO", "DEBUG"):
            self.logger.logger.setLevel(level)
            passwords = [secrets.token_urlsafe(24) for _ in range(4)]
            admin, target, peer = [self.users.create("reset_"+uuid.uuid4().hex,
                PASSWORD_HASHER.hash(passwords[i]), role="administrator" if i == 0 else "standard") for i in range(3)]
            admin_headers = self.login(admin.username, passwords[0])
            old_tokens = [self.login(target.username, passwords[1]) for _ in range(2)]
            peer_headers = self.login(peer.username, passwords[2])
            url = f"/users/{target.id}/password"
            payload = {"new_password": passwords[3]}
            before = self.users.get_by_id(target.id)
            self.assertEqual(self.client.put(url, json=payload).status_code, 401)
            self.assertEqual(self.client.put(url, headers=peer_headers, json=payload).status_code, 403)
            self.assertEqual(self.client.put(f"/users/{admin.id}/password", headers=admin_headers, json=payload).status_code, 400)
            self.assertEqual(self.client.put("/users/9223372036854775807/password", headers=admin_headers, json=payload).status_code, 404)
            self.assertEqual(self.client.put(url, headers=admin_headers, json={"new_password": ""}).status_code, 422)
            response = self.client.put(url, headers=admin_headers, json=payload)
            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.content, b"")
            changed = self.users.get_by_id(target.id)
            self.assertEqual(changed.credential_version, before.credential_version+1)
            self.assertTrue(PASSWORD_HASHER.verify(changed.password_hash, passwords[3]))
            self.assertEqual(changed.role, before.role)
            for token in old_tokens:
                self.assertEqual(self.client.get("/test", headers=token).status_code, 401)
            self.assertEqual(self.client.post("/token", data={"username":target.username,"password":passwords[1]}).status_code,401)
            self.login(target.username, passwords[3])
            self.assertEqual(self.client.get("/test", headers=peer_headers).status_code, 200)
            self.assertEqual(self.client.get("/users", headers=admin_headers).status_code, 200)
            # Simulate a role/password change between dependency validation and
            # the store transaction: locked revalidation must still reject it.
            self.users.change_password(admin.id, 1, passwords[0], passwords[3])
            with self.assertRaises(UserManagementError) as stale:
                self.users.reset_password(admin.id, 1, target.id, changed.password_hash)
            self.assertEqual(stale.exception.status, 401)
            with self.provider.connection() as connection, connection.cursor() as cursor:
                cursor.execute("UPDATE public.api_users SET role='standard' WHERE id=%s", (admin.id,))
            with self.assertRaises(UserManagementError) as demoted:
                self.users.reset_password(admin.id, 2, target.id, changed.password_hash)
            self.assertEqual(demoted.exception.status, 403)
            self.assertEqual(self.users.get_by_id(target.id).credential_version, changed.credential_version)
            lines = [line for line in self.output.getvalue().splitlines() if response.headers["X-Interaction-ID"] in line]
            self.assertEqual(sum(" | API password reset | " in line for line in lines), 1)
            self.assertTrue(any('"administrator_id": '+str(admin.id) in line and '"user_id": '+str(target.id) in line and '"outcome": "completed"' in line for line in lines))
            for value in passwords+[before.password_hash, changed.password_hash]+[h["Authorization"].split(" ",1)[1] for h in old_tokens]:
                self.assertNotIn(value, self.output.getvalue())

    def test_16_reset_collection_http_replay(self):
        """Replay public reset request definitions with random disposable accounts."""
        import re
        from app.api_credentials import PASSWORD_HASHER
        variables = {"base_url":"http://testserver", "admin_username":"reset_admin_"+uuid.uuid4().hex,
                     "reset_admin_password":secrets.token_urlsafe(24), "reset_peer_username":"reset_peer_"+uuid.uuid4().hex,
                     "reset_peer_password":secrets.token_urlsafe(24), "reset_target_username":"reset_target_"+uuid.uuid4().hex,
                     "reset_old_password":secrets.token_urlsafe(24), "reset_new_password":secrets.token_urlsafe(24)}
        self.users.create(variables["admin_username"], PASSWORD_HASHER.hash(variables["reset_admin_password"]),role="administrator")
        self.users.create(variables["reset_peer_username"], PASSWORD_HASHER.hash(variables["reset_peer_password"]))
        items = json.loads((PROJECT_ROOT/"postman/Ouroboros.postman_collection.json").read_text(encoding="utf-8"))["item"][11]["item"]
        def expand(value):
            return re.sub(r"\{\{([^}]+)\}\}",lambda match:variables[match[1]],value)
        for item in items[1:]:
            spec=item["request"]
            options={}
            if spec["auth"]["type"] == "bearer":
                options["headers"]={"Authorization":"Bearer "+expand(spec["auth"]["bearer"][0]["value"])}
            body=spec.get("body",{})
            if body.get("mode") == "raw": options["json"]=json.loads(expand(body["raw"]))
            if body.get("mode") == "urlencoded": options["data"]={p["key"]:expand(p["value"]) for p in body["urlencoded"]}
            response=self.client.request(spec["method"],expand(spec["url"]["raw"] if isinstance(spec["url"], dict) else spec["url"]),**options)
            script=next(e["script"]["exec"] for e in item["event"] if e["listen"] == "test")
            expected=int(re.search(r"status\((\d+)\)",script[0])[1])
            self.assertEqual(response.status_code,expected,item["name"])
            if expected == 204: self.assertEqual(response.content,b"")
            capture={62:"reset_admin_token",63:"reset_target_id",64:"reset_target_old_token",65:"reset_peer_token",73:"reset_target_new_token"}.get(int(item["name"][:2]))
            if capture: variables[capture]=str(response.json()["id" if expected == 201 else "access_token"])

    def test_17_concurrent_reset_and_self_service(self):
        """Competing resets/self-service serialize without lost version increments."""
        from app.api_credentials import PASSWORD_HASHER
        passwords=[secrets.token_urlsafe(24) for _ in range(4)]
        admin=self.users.create("reset_race_admin_"+uuid.uuid4().hex,PASSWORD_HASHER.hash(passwords[0]),role="administrator")
        target=self.users.create("reset_race_target_"+uuid.uuid4().hex,PASSWORD_HASHER.hash(passwords[1]))
        admin_headers=self.login(admin.username,passwords[0])
        target_headers=self.login(target.username,passwords[1])
        barrier=threading.Barrier(2)
        def change(index):
            barrier.wait(timeout=10)
            if index == 0:
                return self.client.put(f"/users/{target.id}/password",headers=admin_headers,json={"new_password":passwords[2]}).status_code
            return self.client.put("/users/me/password",headers=target_headers,json={"current_password":passwords[1],"new_password":passwords[3]}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool: statuses=list(pool.map(change,(0,1)))
        self.assertEqual(statuses[0],204)
        self.assertIn(statuses[1],(204,401))
        final=self.users.get_by_id(target.id)
        self.assertEqual(final.credential_version,2+(statuses[1] == 204))
        self.assertTrue(PASSWORD_HASHER.verify(final.password_hash,passwords[2]))
        self.assertEqual(self.client.get("/test",headers=target_headers).status_code,401)

    def test_14_password_collection_http_replay(self):
        """Replay password definitions and an actual HTTP race, without JS claims."""
        from app.api_credentials import PASSWORD_HASHER
        import re
        variables = {"base_url":"http://testserver"}
        for who,role in (("admin","administrator"),("standard","standard")):
            variables[who+"_username"] = who+"_"+uuid.uuid4().hex
            variables[who+"_password"] = secrets.token_urlsafe(24)
            variables[who+"_new_password"] = secrets.token_urlsafe(24)
            self.users.create(variables[who+"_username"],PASSWORD_HASHER.hash(variables[who+"_password"]),role=role)
        variables.update(standard_next_password_a=secrets.token_urlsafe(24),standard_next_password_b=secrets.token_urlsafe(24))
        collection = json.loads((PROJECT_ROOT/"postman/Ouroboros.postman_collection.json").read_text(encoding="utf-8"))
        items = collection["item"][10]["item"]
        def expand(value):
            return re.sub(r"\{\{([^}]+)\}\}",lambda match:variables[match[1]],value)
        def send(item):
            spec = item["request"]
            options = {"headers":{}}
            if spec["auth"]["type"] == "bearer":
                options["headers"]["Authorization"] = "Bearer "+expand(spec["auth"]["bearer"][0]["value"])
            body = spec.get("body",{})
            if body.get("mode") == "urlencoded": options["data"] = {field["key"]:expand(field["value"]) for field in body["urlencoded"]}
            if body.get("mode") == "raw":
                options["headers"]["Content-Type"] = "application/json"
                options["content"] = expand(body["raw"]).encode("utf-8")
            return self.client.request(spec["method"],expand(spec["url"]["raw"] if isinstance(spec["url"], dict) else spec["url"]),**options)
        captures = {40:"password_admin_old_token",41:"password_standard_old_token",49:"password_standard_new_token",54:"password_admin_new_token"}
        for item in items[:18]:
            response = send(item)
            script = next(event["script"]["exec"] for event in item["event"] if event["listen"] == "test")
            expected = int(re.search(r"status\((\d+)\)",script[0])[1])
            self.assertEqual(response.status_code,expected,item["name"])
            number = int(item["name"][:2])
            if number in captures: variables[captures[number]] = response.json()["access_token"]
            if expected == 204: self.assertEqual(response.content,b"")
        barrier = threading.Barrier(2)
        def racing(item):
            barrier.wait(timeout=10)
            return send(item).status_code
        with ThreadPoolExecutor(max_workers=2) as pool: statuses = list(pool.map(racing,items[18:20]))
        self.assertEqual(sorted(statuses),[204,401])
        self.assertEqual(send(items[20]).status_code,200)

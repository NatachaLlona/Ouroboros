"""API authentication, validation, logging, and lifecycle without normal database writes."""
import contextlib
import io
import json
import secrets
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt
from fastapi.testclient import TestClient

from app.api_credentials import PASSWORD_HASHER, configure_api_credentials, load_signing_secret
from app.auth import AuthService
from support_users import MemoryAPIUsers
from app.config import PROJECT_ROOT, ConfigurationError, load_config
from app.database import DatabaseError
from app.logger import ApplicationLogger
from app.main import create_app


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(20)
        cls.password_hash = PASSWORD_HASHER.hash(cls.password)

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = json.loads((PROJECT_ROOT / ".app.config.example").read_text())
        self.users = MemoryAPIUsers()
        self.user = self.users.create("unit_api_user", self.password_hash)
        self.secret = secrets.token_urlsafe(64)
        self.auth = AuthService(self.config["auth"], self.secret, self.users)
        self.output = io.StringIO()
        self.logger = ApplicationLogger(self.config["logging"], root=self.root, stream=self.output)
        self.addCleanup(self.logger.close)
        self.database = MagicMock()
        self.app = create_app(self.config, self.database, self.auth, self.logger)
        self.client = TestClient(self.app, raise_server_exceptions=False)
        from support_log_evidence import assert_response_logs
        self.client.event_hooks["response"].append(lambda response: assert_response_logs(self,response,self.output.getvalue,self.logger))
        self.addCleanup(self.client.close)

    def bearer(self, scope=None):
        response = self.client.post("/token", data={"username": "unit_api_user", "password": self.password,
                                                   **({"scope": scope} if scope is not None else {})})
        self.assertEqual(response.status_code, 200)
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def test_health_public_and_unavailable(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.database.connection.side_effect = DatabaseError("private backend data")
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'DATABASE_UNAVAILABLE')
        self.assertTrue(response.headers["X-Interaction-ID"])
        self.assertNotIn("private backend data", self.output.getvalue())

    def test_token_claims_credentials_and_scopes(self):
        response = self.client.post("/token", data={"username": "unit_api_user", "password": self.password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["expires_in"], 1800)
        payload = self.auth.decode(response.json()["access_token"])
        self.assertEqual(set(payload["scopes"]), {"test:read", "test:write"})
        self.assertEqual(payload["exp"] - payload["iat"], 1800)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        for username, password in (("unit_api_user", "wrong"), ("unknown", self.password)):
            denied = self.client.post("/token", data={"username": username, "password": password})
            self.assertEqual(denied.status_code, 401)
            self.assertEqual(denied.json()['error']['code'], 'INVALID_CREDENTIALS')
        denied = self.client.post("/token", data={"username": "unit_api_user", "password": self.password, "scope": "admin"})
        self.assertEqual(denied.status_code, 403)

    def test_authentication_and_scope_enforcement(self):
        for headers in ({}, {"Authorization": "Bearer invalid"}, {"Authorization": "Basic invalid"}):
            response = self.client.get("/test", headers=headers)
            self.assertEqual(response.status_code, 401)
            self.assertIn("Bearer", response.headers["WWW-Authenticate"])
        denied = self.client.post("/test", headers=self.bearer("test:read"), json={"value": "entry"})
        self.assertEqual(denied.status_code, 403)
        self.assertIn("test:write", denied.headers["WWW-Authenticate"])
        denied = self.client.get("/test", headers=self.bearer("test:write"))
        self.assertEqual(denied.status_code, 403)

    def test_reject_jwt_claims_and_algorithm(self):
        now = int(time.time())
        base = {"sub": str(self.user.id), "ver": 2, "db": "unit_test", "credential_version": 1, "iat": now, "exp": now + 60,
                "iss": self.config["auth"]["issuer"], "aud": self.config["auth"]["audience"],
                "scopes": ["test:read"]}
        for change in ({"iat": now-120, "exp": now-60}, {"iss": "other"}, {"aud": "other"},
                       {"sub": "other"}, {"scopes": ["admin"]}, {"iat": now+60}, {"scopes": "test:read"},
                       {"credential_version":0}, {"credential_version":True}, {"credential_version":"1"}, {"credential_version":2}):
            token = jwt.encode({**base, **change}, self.secret, algorithm="HS256")
            self.assertEqual(self.client.get("/test", headers={"Authorization": "Bearer " + token}).status_code, 401)
        for algorithm, secret in (("HS384", self.secret), ("HS256", secrets.token_urlsafe(64))):
            token = jwt.encode(base, secret, algorithm=algorithm)
            self.assertEqual(self.client.get("/test", headers={"Authorization": "Bearer " + token}).status_code, 401)
        del base["exp"]
        token = jwt.encode(base, self.secret, algorithm="HS256")
        self.assertEqual(self.client.get("/test", headers={"Authorization": "Bearer " + token}).status_code, 401)

    def test_strict_json_validation_and_content_preservation(self):
        headers = self.bearer()
        malformed = self.client.post("/test", content=b"{", headers={**headers, "Content-Type": "application/json"})
        self.assertEqual(malformed.status_code, 422)
        self.assertNotIn("input", malformed.json()["error"]["details"][0])
        for data in ({}, {"value": None}, {"value": 1}, {"value": {}}, {"value": []}, {"value": "x", "typo": True}):
            response = self.client.post("/test", json=data, headers=headers)
            self.assertEqual(response.status_code, 422)
            self.assertTrue(response.headers["X-Interaction-ID"])
        for value in ("", "  unchanged  ", "x" * 50001):
            with patch("app.endpoints.test.TestRepository.create", return_value={'id':42,'value':value,'created_at':None,'created_at_timezone':None}) as insert:
                response = self.client.post("/test", json={"value": value}, headers=headers)
                self.assertEqual(response.status_code, 201)
                self.assertEqual({key:response.json()[key] for key in ('id','value')}, {"id": 42, "value": value})
                self.assertEqual(insert.call_args.args[0].value, value)
        for entry_id in ("0", "-1", "1.0", "1.5", "bad", "9223372036854775808"):
            self.assertEqual(self.client.get("/test", params={"id": entry_id}, headers=headers).status_code, 422)

    def test_request_ids_errors_and_secret_free_logs(self):
        token_headers = self.bearer()
        secret_value = "request-content-must-not-be-logged"
        with patch("app.endpoints.test.page_entries", side_effect=RuntimeError(secret_value)):
            failure = self.client.get("/test", params={"value": secret_value}, headers={**token_headers, "X-Interaction-ID": "untrusted"})
        self.assertEqual(failure.status_code, 500)
        interaction = failure.headers["X-Interaction-ID"]
        self.assertNotEqual(interaction, "untrusted")
        relevant = [line for line in self.output.getvalue().splitlines() if interaction in line]
        self.assertGreaterEqual(len(relevant), 3)
        self.assertTrue(any('HTTP request finished' in line and '"status": 500' in line for line in relevant))
        self.assertTrue(any('HTTP request finished' in line and '"duration_ms"' in line for line in relevant))
        invalid = self.client.post("/token", data={"password": self.password})
        self.assertEqual(invalid.status_code, 422)
        logs = self.output.getvalue()
        for value in (self.password, self.secret, token_headers["Authorization"], secret_value, self.password_hash):
            self.assertNotIn(value, logs)
        self.assertNotIn(self.password, invalid.text)
        self.assertNotIn(secret_value, failure.text)
        self.assertTrue(self.client.get("/missing").headers["X-Interaction-ID"])

    def test_openapi_and_shutdown(self):
        schema = self.client.get("/openapi.json").json()
        security = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]
        self.assertEqual(set(security["scopes"]), {"test:read", "test:write", "users:manage", "catalogue:access"})
        self.assertEqual(schema["paths"]["/test"]["get"]["security"], [{"OAuth2PasswordBearer": ["test:read"]}])
        self.assertEqual(self.client.get("/docs").status_code, 200)
        with TestClient(self.app):
            pass
        self.database.close.assert_called_once()
        self.assertIsNone(self.auth.secret)
        self.assertIn("API stopped", self.output.getvalue())

    def test_auth_configuration_validation_and_custom_lifetime(self):
        for field, value in (("token_ttl_seconds", 0), ("token_ttl_seconds", True),
                             ("token_ttl_seconds", "1800"), ("issuer", ""),
                             ("audience", " "), ("password_hash", "not-an-argon2-hash")):
            config = json.loads(json.dumps(self.config))
            config["auth"][field] = value
            (self.root / ".app.config").write_text(json.dumps(config))
            with self.assertRaises(ConfigurationError):
                load_config(self.root)
        self.auth.config["token_ttl_seconds"] = 321
        issued = self.auth.issue(self.user, ["test:read"])
        payload = self.auth.decode(issued["access_token"])
        self.assertEqual(issued["expires_in"], 321)
        self.assertEqual(payload["exp"] - payload["iat"], 321)

    def test_credential_enrollment_and_cancellation(self):
        config = json.loads(json.dumps(self.config))
        with patch("builtins.input", side_effect=["create", "additional_user"]), \
             patch("app.api_credentials.read_password", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                configure_api_credentials(config, self.users, self.root)
        self.assertEqual(self.users.count(), 1)
        with patch("builtins.input", side_effect=["create", "additional_user"]), \
             patch("app.api_credentials.read_password", return_value=self.password):
            configure_api_credentials(config, self.users, self.root)
        self.assertEqual(self.users.count(), 2)
        self.assertEqual(config["api_users"]["last_api_username"], "additional_user")
        self.assertTrue(PASSWORD_HASHER.verify(self.users.get_by_username("additional_user").password_hash, self.password))

    def test_swagger_form_contract_and_empty_values(self):
        schema=self.client.get("/openapi.json").json()
        endpoint=schema["paths"]["/token"]["post"]
        self.assertNotIn("security",endpoint)
        self.assertNotIn("security",schema["paths"]["/health"]["get"])
        reference=endpoint["requestBody"]["content"]["application/x-www-form-urlencoded"]["schema"]["$ref"]
        form=schema["components"]["schemas"][reference.split("/")[-1]]
        self.assertEqual(set(form["required"]),{"username","password"})
        self.assertEqual(form["properties"]["grant_type"]["default"],"password")
        self.assertEqual(form["properties"]["grant_type"]["const"],"password")
        self.assertIn("space-separated",form["properties"]["scope"]["description"])
        self.assertIn("Not used",form["properties"]["client_id"]["description"])
        self.assertEqual(form["properties"]["password"]["format"],"password")
        flow=schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]
        self.assertEqual(flow["tokenUrl"],"/token")
        self.assertEqual(set(flow["scopes"]),{"test:read","test:write","users:manage","catalogue:access"})
        for fields in ({},{"grant_type":"password","scope":"test:read test:write","client_id":"","client_secret":""},
                       {"grant_type":"","scope":"","client_id":"","client_secret":""}):
            response=self.client.post("/token",data={"username":"unit_api_user","password":self.password,**fields})
            self.assertEqual(response.status_code,200)
            self.assertEqual(set(self.auth.decode(response.json()["access_token"])["scopes"]),{"test:read","test:write"})
        for value in ("string","client_credentials","password "):
            response=self.client.post("/token",data={"username":"unit_api_user","password":self.password,"grant_type":value})
            self.assertEqual(response.status_code,422)
        for field in ("username","password"):
            response=self.client.post("/token",data={"username":"unit_api_user","password":self.password,field:""})
            self.assertEqual(response.status_code,422)
        self.assertNotIn(self.password,self.output.getvalue())

    def test_lifespan_cleanup_continues_after_close_failure(self):
        self.database.close.side_effect=RuntimeError("private-cleanup-detail")
        with patch.object(self.auth,"close",wraps=self.auth.close) as close_auth:
            with TestClient(self.app):
                pass
            close_auth.assert_called_once()
        self.assertTrue(self.app.state.cleanup_failures)
        self.assertIsNone(self.auth.secret)
        self.assertNotIn("private-cleanup-detail",self.output.getvalue())

    def test_credentials_and_signing_key_persistence(self):
        config = json.loads((PROJECT_ROOT / ".app.config.example").read_text())
        users = MemoryAPIUsers()
        with patch("builtins.input", return_value="local_api_user"), patch("app.api_credentials.read_password", return_value=self.password):
            configure_api_credentials(config, users, self.root)
        self.assertTrue(users.get_by_username("local_api_user").password_hash.startswith("$argon2id$"))
        content = (self.root / ".app.config").read_text()
        self.assertNotIn(self.password, content)
        self.assertNotIn("password_hash", content)
        with patch("builtins.input", return_value="y"), patch("app.api_credentials.read_password") as prompt:
            configure_api_credentials(config, users, self.root)
            prompt.assert_not_called()
        self.assertEqual(users.count(), 1)
        key = load_signing_secret(self.root)
        self.assertEqual(load_signing_secret(self.root), key)
        self.assertGreaterEqual(len(key), 64)

    def test_shared_pagination_validation_and_envelope(self):
        headers = self.bearer()
        from app.datetimes import present
        expected = {"count": 17, "page": 2, "page_size": 10, "items": [present({"id": 42, "value": "entry",'created_at':None,'created_at_timezone':None})]}
        with patch("app.endpoints.test.page_entries", return_value=expected) as listing:
            response = self.client.get("/test?page=2&page_size=10&id=42&value=%25entry%25", headers=headers)
            self.assertEqual(response.json(), expected)
            self.assertEqual({key:listing.call_args.kwargs[key] for key in ('page','page_size','order_by','order_direction')}, {"page": 2, "page_size": 10, "order_by": "id", "order_direction": "asc"})
            self.assertEqual((listing.call_args.kwargs['entry_id'],listing.call_args.kwargs['value']), (42, "%entry%"))
        for query in ("page=0", "page=-1", "page=1.0", "page=oops", "page_size=9", "page_size=51", "page_size=10.0", "page_size=true"):
            response = self.client.get("/test?"+query, headers=headers)
            self.assertEqual(response.status_code, 422, query)
            detail = response.json()["error"]["details"][0]
            self.assertIn("loc", detail)
            self.assertIn("type", detail)
            self.assertNotEqual(detail["msg"], "Invalid request field")
            self.assertNotIn("input", detail)
            self.assertNotIn("ctx", detail)

    def test_current_role_authorization_and_future_scope(self):
        from dataclasses import replace
        from fastapi import Security
        from app.auth import require_scopes

        @self.app.get("/future", dependencies=[Security(require_scopes, scopes=["future:operation"])])
        def future():
            return {"ok": True}

        headers = self.bearer("test:read")
        self.assertEqual(self.client.get("/future", headers=headers).status_code, 403)
        self.users.users[self.user.id] = replace(self.user, role="administrator")
        self.assertEqual(self.client.get("/future", headers=headers).status_code, 200)
        self.users.page = MagicMock(return_value={"count": 0, "page": 1, "page_size": 50, "items": []})
        self.assertEqual(self.client.get("/users", headers=headers).status_code, 200)
        self.users.users[self.user.id] = self.user
        # The already-issued token cannot freeze administrator rights.
        self.assertEqual(self.client.get("/users", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/future", headers=headers).status_code, 403)
        self.users.users[self.user.id] = replace(self.user, role="administrator", is_active=False)
        self.assertEqual(self.client.get("/users", headers=headers).status_code, 401)

    def test_administrative_input_is_secret_free_and_strict(self):
        from dataclasses import replace
        from datetime import datetime, timezone
        self.users.users[self.user.id] = replace(self.user, role="administrator")
        headers = self.bearer("test:read")
        public = {"id": 2, "username": "new-user", "role": "standard", "is_active": True, "created_at": datetime.now(timezone.utc)}
        self.users.create_managed = MagicMock(return_value=public)
        secret = "private-user-create-password-🐍"
        response = self.client.post("/users", json={"username": "new-user", "password": secret}, headers=headers)
        self.assertEqual(response.status_code, 201, response.text)
        args = self.users.create_managed.call_args.args
        self.assertTrue(PASSWORD_HASHER.verify(args[2], secret))
        self.assertEqual(args[3], "standard")
        for body in ({"username": "new-user"}, {"username": "new-user", "password": 123},
                     {"username": "new-user", "password": secret, "role": "owner"},
                     {"username": "", "password": secret}, {"username": "new-user", "password": ""},
                     {"username": "new-user", "password": secret, "password_hash": "hidden-hash"}):
            rejected = self.client.post("/users", json=body, headers=headers)
            self.assertEqual(rejected.status_code, 422, rejected.text)
            self.assertNotIn(secret, rejected.text)
        for level in ("INFO", "DEBUG"):
            self.logger.logger.setLevel(level)
            self.users.create_managed.side_effect = RuntimeError(secret)
            response = self.client.post("/users", json={"username": "new-user", "password": secret}, headers=headers)
            self.assertEqual(response.status_code, 500)
        self.assertEqual(self.client.put(f"/users/{self.user.id}/role", json={"role":"owner"}, headers=headers).status_code, 422)
        for value in (secret, args[2], "hidden-hash"):
            self.assertNotIn(value, self.output.getvalue())
            self.assertNotIn(value, response.text)

    def test_openapi_administration_and_page_contract(self):
        schema = self.app.openapi()
        for path, method in (("/users", "get"), ("/users", "post"), ("/users/{id}/role", "put")):
            self.assertEqual(schema["paths"][path][method]["security"], [{"OAuth2PasswordBearer": ["users:manage"]}])
        params = {item["name"]: item["schema"] for item in schema["paths"]["/users"]["get"]["parameters"]}
        self.assertEqual(params["page"]["default"], 1)
        self.assertEqual(params["page_size"]["default"], 50)
        self.assertEqual(params["page_size"]["minimum"], 10)
        self.assertEqual(params["page_size"]["maximum"], 50)
        self.assertNotIn("password_hash", schema["components"]["schemas"]["PublicUser"]["properties"])
        self.assertEqual(schema["components"]["schemas"]["UserCreate"]["properties"]["password"]["format"], "password")
        self.assertEqual(schema["paths"]["/users/me/password"]["put"]["security"],[{"OAuth2PasswordBearer":[]}])
        self.assertNotIn("content",schema["paths"]["/users/me/password"]["put"]["responses"]["204"])

    def test_reset_password_validation_authorization_and_log_exclusion(self):
        from dataclasses import replace
        from app.api_users import UserManagementError
        self.users.reset_password = MagicMock()
        standard = self.bearer()
        body = {"new_password": "reset-secret-value"}
        self.assertEqual(self.client.put("/users/2/password", json=body).status_code, 401)
        self.assertEqual(self.client.put("/users/2/password", headers=standard, json=body).status_code, 403)
        self.users.users[self.user.id] = replace(self.user, role="administrator")
        admin = self.bearer()
        for level in ("INFO", "DEBUG"):
            self.logger.logger.setLevel(level)
            for invalid in ({}, {"new_password": ""}, {"new_password": 1},
                            {"new_password": None}, {**body, "unexpected": "must-never-be-previewed"}):
                self.assertEqual(self.client.put("/users/2/password", headers=admin, json=invalid).status_code, 422)
            self.assertEqual(self.client.put("/users/2/password", headers={**admin, "Content-Type": "application/json"},
                content=b'{"unexpected":"malformed-secret",').status_code, 422)
            response = self.client.put("/users/2/password", headers=admin, json=body)
            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.content, b"")
            args = self.users.reset_password.call_args.args
            self.assertEqual(args[:3], (self.user.id, 1, 2))
            self.assertTrue(PASSWORD_HASHER.verify(args[3], body["new_password"]))
            for status in (400, 401, 403, 404):
                self.users.reset_password.side_effect = UserManagementError(status, "Safe rejection")
                self.assertEqual(self.client.put("/users/2/password", headers=admin, json=body).status_code, status)
            self.users.reset_password.side_effect = None
        output = self.output.getvalue()
        self.assertNotIn(body["new_password"], output)
        self.assertNotIn("must-never-be-previewed", output)
        self.assertNotIn("malformed-secret", output)
        self.assertFalse(any("Request JSON body received" in line for line in output.splitlines() if "PUT /users/2/password" in line))
        self.assertIn("API password reset", output)

    def test_swagger_explicit_query_parameters(self):
        schema = self.app.openapi()
        for path, names in (("/test", {"id", "value", "created_at", "created_at_timezone", "created_at_date", "filter_timezone", "created_at_from", "created_at_to", "display_timezone", "page", "page_size", "order_by", "order_direction"}),
                            ("/users", {"page", "page_size", "order_by", "order_direction"})):
            params = schema["paths"][path]["get"]["parameters"]
            self.assertEqual({p["name"] for p in params}, names)
            for param in params:
                self.assertEqual(param["in"], "query")
                self.assertFalse(param["required"])
                self.assertTrue(param["description"])
                self.assertTrue(param["schema"]["examples"])
        reset = schema["paths"]["/users/{id}/password"]["put"]
        self.assertEqual(reset["security"], [{"OAuth2PasswordBearer": ["users:manage"]}])
        self.assertNotIn("content", reset["responses"]["204"])

    def test_password_body_exclusion_and_version_revocation(self):
        from dataclasses import replace
        headers = self.bearer("test:read")
        self.users.change_password = MagicMock()
        secret = "body-must-be-omitted-🐍"
        response = self.client.put("/users/me/password",headers=headers,json={"current_password":self.password,"new_password":secret})
        self.assertEqual(response.status_code,204)
        self.assertEqual(response.content,b"")
        self.assertEqual(self.users.change_password.call_args.args,(self.user.id,1,self.password,secret))
        lines = [line for line in self.output.getvalue().splitlines() if "PUT /users/me/password" in line]
        self.assertFalse(any("Request JSON body received" in line for line in lines))
        self.assertNotIn(secret,self.output.getvalue())
        self.users.users[self.user.id] = replace(self.user,credential_version=2)
        self.assertEqual(self.client.get("/test",headers=headers).status_code,401)


if __name__ == "__main__":
    unittest.main()

"""Legacy migration safety and independent database/master prompts."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from app.api_credentials import PASSWORD_HASHER, migrate_legacy_user
from app.config import PROJECT_ROOT, ConfigurationError, save_config
from app.credentials import prompt_credentials
from app.database import DatabaseError
from support_users import MemoryAPIUsers


class UserMigrationTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root=Path(directory.name)
        self.config=json.loads((PROJECT_ROOT/".app.config.example").read_text())
        self.hash=PASSWORD_HASHER.hash("unit-only-migration-password")
        self.config["auth"].update(username="legacy_user",password_hash=self.hash)
        # This single file represents the preexisting configuration, not a backup.
        (self.root/".app.config").write_text(json.dumps(self.config))

    def test_import_before_removal_idempotent_and_no_hash_copies(self):
        users=MemoryAPIUsers()
        migrate_legacy_user(self.config,users,self.root)
        self.assertEqual(users.get_by_username("legacy_user").password_hash,self.hash)
        self.assertEqual(users.count(),1)
        migrate_legacy_user(self.config,users,self.root)
        self.assertEqual(users.count(),1)
        self.assertNotIn("password_hash",(self.root/".app.config").read_text())
        self.assertNotIn("username",self.config["auth"])
        self.assertEqual(self.config["api_users"],{"last_api_username":"legacy_user"})
        self.assertEqual([p.name for p in self.root.iterdir()],[".app.config"])

    def test_conflict_preserves_original_configuration(self):
        users=MemoryAPIUsers()
        users.create("legacy_user",PASSWORD_HASHER.hash("different-unit-password"))
        before=(self.root/".app.config").read_bytes()
        with self.assertRaises(DatabaseError):migrate_legacy_user(self.config,users,self.root)
        self.assertEqual((self.root/".app.config").read_bytes(),before)
        self.assertEqual(self.config["auth"]["password_hash"],self.hash)
        self.assertEqual(users.count(),1)
        with self.assertRaises(ConfigurationError):save_config(self.config,self.root)
        self.assertEqual(len(list(self.root.iterdir())),1)

    def test_database_and_master_selection_are_independent(self):
        self.config["database"].update(name="original_database",user="original_master")
        for answers,expected_name,expected_user in ((["n","other_database","y"],"other_database","original_master"),
                                                     (["y","n","other_master"],"original_database","other_master")):
            config=json.loads(json.dumps(self.config))
            prompts=[]
            def reply(prompt):
                prompts.append(prompt)
                return answers.pop(0)
            with patch("app.credentials.sys.stdin.isatty",return_value=True), patch("builtins.input",side_effect=reply), patch("app.credentials.read_password",return_value="unit-only"):
                prompt_credentials(config,self.root)
            self.assertIn("database",prompts[0])
            self.assertTrue(any("master" in prompt for prompt in prompts[1:]))
            self.assertEqual(config["database"]["name"],expected_name)
            self.assertEqual(config["database"]["user"],expected_user)
        self.assertEqual(len(list(self.root.iterdir())),1)

"""Configuration boundary, naming and surgical JSONC repair checks."""
import copy
import tempfile
from pathlib import Path
import unittest

from database.documentation import example
from database.secrets import validate_password
from database.settings import (ConfigurationError, mapping, read_jsonc, repair_prefix,
                               structural_identity, validate_operational, validate_provisioning)


class SettingsTests(unittest.TestCase):
    def test_interactive_conflict_repair_and_noninteractive_rejection(self):
        import json
        from unittest.mock import patch
        from database.runtime import prepare
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'modules/database').mkdir(parents=True)
            source = Path(__file__).resolve().parents[3]
            (root/'modules/database/config.jsonc').write_text((source/'modules/database/config.example.jsonc').read_text(encoding='utf-8'),encoding='utf-8')
            document = example()
            document['prefixes'] = dict(document['prefixes'],work='QA')
            path = root/'provisioning.jsonc'
            text = '// preserve operator notes\n'+json.dumps(document,indent=2)
            path.write_text(text,encoding='utf-8')
            with patch('sys.stdin.isatty',return_value=False), self.assertRaises(ConfigurationError):
                prepare(root,allow_repair=True,can_repair=True)
            self.assertEqual(path.read_text(encoding='utf-8'),text)
            with patch('sys.stdin.isatty',return_value=True), patch('builtins.input',side_effect=['work','BX']):
                repaired,_ = prepare(root,allow_repair=True,can_repair=True)
            self.assertEqual(repaired['prefixes']['work'],'BX')
            self.assertIn('// preserve operator notes',path.read_text(encoding='utf-8'))
            path.write_text(text,encoding='utf-8')
            with patch('sys.stdin.isatty',return_value=True), self.assertRaises(ConfigurationError):
                prepare(root,allow_repair=True,can_repair=False)

    def test_jsonc_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.jsonc'
            path.write_text('{/* real comment */ "url":"https://example.test/a/*b*/", // line\n "nested":{"a":1}}',encoding='utf-8')
            self.assertEqual(read_jsonc(path)['nested'], {'a':1})
            for text in ('{"a":1,"a":2}', '{"nested":{"a":1,"a":2}}', '{"a":NaN}', '{/* unfinished'):
                path.write_text(text,encoding='utf-8')
                with self.assertRaises(ConfigurationError):
                    read_jsonc(path)

    def test_provisioning_types_unknown_names_and_prefixes(self):
        validate_provisioning(example())
        for key, value in (('format_version',True),('base_quantity_digits','7'),('schema','public'),('database_name','unsafe-name')):
            document = example()
            document[key] = value
            with self.assertRaises(ConfigurationError):
                validate_provisioning(document)
        document = example()
        document['extra'] = 1
        with self.assertRaises(ConfigurationError):
            validate_provisioning(document)
        for prefix in ('QA','aB','ÁB',''):
            document = example()
            document['prefixes'] = dict(document['prefixes'], work=prefix)
            with self.assertRaises(ConfigurationError):
                validate_provisioning(document)

    def test_vocabulary_collision_and_alternate(self):
        document = example()
        document['vocabulary']['work']['name'] = 'book'
        document['vocabulary']['activity']['name'] = 'read'
        names = mapping(validate_provisioning(document))
        self.assertEqual(names['watch_list_entry'],'read_list_entry')
        self.assertEqual(names['work_tag'],'book_tag')
        self.assertEqual(names['api_user'],'api_user')
        document['vocabulary']['work']['name'] = 'test'
        with self.assertRaises(ConfigurationError):
            validate_provisioning(document)

    def test_comments_do_not_change_identity_and_repair_preserves_them(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.jsonc'
            before = '// retained comment\n'+json.dumps(example(),indent=2)+'\n/* retained end */\n'
            path.write_text(before,encoding='utf-8')
            first = structural_identity(read_jsonc(path))
            path.write_text('// another comment\n'+before,encoding='utf-8')
            self.assertEqual(first,structural_identity(read_jsonc(path)))
            repair_prefix(path,'work','BX')
            self.assertIn('// retained comment',path.read_text(encoding='utf-8'))
            self.assertIn('/* retained end */',path.read_text(encoding='utf-8'))
            self.assertNotEqual(first,structural_identity(read_jsonc(path)))

    def test_operational_strictness(self):
        root = Path(__file__).resolve().parents[3]
        document = read_jsonc(root/'modules/database/config.example.jsonc')
        self.assertEqual(validate_operational(document)['published_address'],'127.0.0.1')
        for key,value in (('published_port',6668),('published_port',True),('published_address','0.0.0.0'),('secret_file','password'),('master_user','ouroboros_owner')):
            invalid = copy.deepcopy(document)
            invalid[key] = value
            with self.assertRaises(ConfigurationError):
                validate_operational(invalid)

    def test_human_password_policy(self):
        # Public synthetic values are confined to validation tests, never credentials.
        validate_password('Aa12345!')
        for invalid in ('short','aaaaaaaa','AA12345!','aa12345!','Aaabcdef!','Aa123456','Aa1234567890123456!'):
            with self.assertRaises(ConfigurationError):
                validate_password(invalid)


if __name__ == '__main__':
    unittest.main()

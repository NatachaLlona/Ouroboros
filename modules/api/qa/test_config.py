"""Configuration and startup routing checks without credentials or a database."""
import copy
from decimal import Decimal
import json
import tempfile
import unittest
from database.settings import ConfigurationError
from api.service.config import load,effective
from support_config import basic_api_configuration


class ConfigurationTests(unittest.TestCase):

    def test_types_duplicates_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root=basic_api_configuration(directory)
            settings=load(root)
            path=root/'modules/api/config.jsonc'
            for key,value in (('port',6968),('max_connections',True),('host','0.0.0.0'),('extra',1)):
                invalid=copy.deepcopy(settings)
                invalid[key]=value
                path.write_text(json.dumps(invalid),encoding='utf-8')
                with self.assertRaises(ConfigurationError):
                    load(root)
            path.write_text('{"port":6969,"port":6969}',encoding='utf-8')
            with self.assertRaises(ConfigurationError):
                load(root)

    def test_persisted_values_require_operator_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            settings=load(basic_api_configuration(directory))
            record={'name':'batch_items','minimum_value':Decimal(1),'maximum_value':Decimal(300),'current_value':Decimal(25)}
            self.assertEqual(effective(settings,[record])['batch_items'],25)
            for value in (Decimal(301),Decimal('NaN'),Decimal('1.5')):
                record['current_value']=value
                with self.assertRaises(ConfigurationError):
                    effective(settings,[record])

    def test_tls_configuration_is_strict_and_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root=basic_api_configuration(directory)
            settings=load(root)
            for field,value in (('server_name',True),('server_name','https://localhost'),
                                ('certificate_file',''),('private_key_file',None),('extra','value')):
                invalid=copy.deepcopy(settings)
                invalid['tls'][field]=value
                (root/'modules/api/config.jsonc').write_text(json.dumps(invalid),encoding='utf-8')
                with self.assertRaises(ConfigurationError):
                    load(root)







if __name__=='__main__':
    unittest.main()

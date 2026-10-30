"""Grapheme input limits, unchanged historical reads and isolated real API writes."""
from dataclasses import replace
import json
import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from uniseg.graphemecluster import grapheme_clusters
from app.config import PROJECT_ROOT
from app.schemas.catalogue import RESOURCES
from app.text_limits import DESCRIPTION_MAX_LENGTH, GRAPHEME_UNICODE_VERSION, description_length
import test_api as api
import test_catalogue_api as legacy

DESCRIPTIONS = {
    'tags': ('description_tags', {'tag_name': 'description_case', 'display_name_tags': 'Description test'}),
    'tag_categories': ('description_tag_categories', {'tag_category_name': 'description_case', 'display_name_tag_categories': 'Description test'}),
    'work_classifications': ('description_work_classifications', {'work_classification_name': 'description_case', 'display_name_work_classifications': 'Description test'}),
}


class DescriptionContractTests(unittest.TestCase):
    def test_shared_unicode_conformance_and_generated_limit(self):
        fixture = json.loads((PROJECT_ROOT/'qa/grapheme-vectors.json').read_text(encoding='utf-8'))
        self.assertEqual(fixture['unicode_version'], GRAPHEME_UNICODE_VERSION)
        for vector in fixture['cases']:
            self.assertEqual(list(grapheme_clusters(vector['text'])), vector['segments'])
            self.assertEqual(description_length(vector['text']), len(vector['segments']))
        generated = (PROJECT_ROOT/'frontend/src/app/shared/text-limits.generated.ts').read_text(encoding='utf-8')
        self.assertIn(f'DESCRIPTION_MAX_LENGTH = {DESCRIPTION_MAX_LENGTH};', generated)
        self.assertIn(json.dumps(GRAPHEME_UNICODE_VERSION), generated)

    def test_all_description_inputs_limit_graphemes_without_limiting_other_text_or_outputs(self):
        for table, (field, base) in DESCRIPTIONS.items():
            resource = RESOURCES[table]
            for unit in ('x', ' ', 'e\u0301', '👩🏽‍💻', '👨‍👩‍👧‍👦', '🇵🇹'):
                text = unit * DESCRIPTION_MAX_LENGTH
                self.assertEqual(resource.create.model_validate({**base, field: text}).model_dump()[field], text)
                self.assertEqual(resource.update.model_validate({field: text}).model_dump(exclude_unset=True)[field], text)
                for model, values in ((resource.create, base), (resource.update, {}), (resource.bulk_update, {})):
                    with self.assertRaises(ValidationError):
                        model.model_validate({**values, field: text + 'x'})
            for value in (None, ''):
                self.assertEqual(resource.create.model_validate({**base, field: value}).model_dump()[field], value)
            other = next(iter(base))
            self.assertNotIn(field, resource.update.model_validate({other:base[other]}).model_dump(exclude_unset=True))
            create_schema = resource.create.model_json_schema()['properties'][field]
            self.assertIn(str(DESCRIPTION_MAX_LENGTH), create_schema['description'])
            self.assertNotIn('maxLength', str(create_schema))
            self.assertEqual(create_schema['anyOf'][0]['x-max-graphemes'], DESCRIPTION_MAX_LENGTH)
            self.assertNotIn('x-max-graphemes', str(resource.record.model_json_schema()['properties'][field]))
        text = 'x' * (DESCRIPTION_MAX_LENGTH + 1)
        self.assertEqual(RESOURCES['works'].create.model_validate({'title':'Title','title_language':'en','synopsis':text}).synopsis, text)
        self.assertEqual(RESOURCES['watchlist_entries'].create.model_validate({'id_works':'WK0000001','observations':text}).observations, text)


class DescriptionHTTPTests(unittest.TestCase):
    setUpClass = classmethod(api.APITests.setUpClass.__func__)
    setUp = api.APITests.setUp

    def test_direct_api_overflow_returns_standard_error_without_mutations(self):
        self.users.users[self.user.id] = replace(self.user, role='administrator')
        headers = api.APITests.bearer(self)
        with patch('app.catalogue_repository.CatalogueRepository.create') as create, \
             patch('app.catalogue_repository.CatalogueRepository.create_many') as create_many, \
             patch('app.catalogue_repository.CatalogueRepository.bulk') as bulk:
            for table, (field, base) in DESCRIPTIONS.items():
                for unit in ('x', ' ', 'e\u0301', '👩🏽‍💻', '👨‍👩‍👧‍👦', '🇵🇹'):
                    response = self.client.post('/'+table, headers=headers, json={**base, field:unit*(DESCRIPTION_MAX_LENGTH+1)})
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()['error']['code'], 'VALIDATION_ERROR')
                batch = self.client.post('/'+table, headers=headers, json=[base, {**base,field:'x'*(DESCRIPTION_MAX_LENGTH+1)}])
                self.assertEqual(batch.status_code, 422)
                changed = self.client.put('/'+table, headers=headers, params={'confirm':True}, json={field:'x'*(DESCRIPTION_MAX_LENGTH+1)})
                self.assertEqual(changed.status_code, 422)
            create.assert_not_called()
            create_many.assert_not_called();bulk.assert_not_called()


@unittest.skipUnless(os.environ.get('FOUNDATION_RUN_INTEGRATION') == '1', 'Requires owned disposable Docker integration')
class DescriptionIntegrationTests(unittest.TestCase):
    setUpClass = classmethod(legacy.CatalogueAPITests.setUpClass.__func__)
    cleanup = classmethod(legacy.CatalogueAPITests.cleanup.__func__)
    setUp = legacy.CatalogueAPITests.setUp

    def test_real_description_crud_legacy_preservation_and_validation_rollback(self):
        headers = self.headers['supervisor']
        for table, (field, base) in DESCRIPTIONS.items():
            valid = '👩🏽‍💻' * DESCRIPTION_MAX_LENGTH
            response = self.client.post('/'+table, headers=headers, json={**base, field:valid})
            self.assertEqual(response.status_code, 201)
            record = response.json();identifier = record['id_'+table]
            self.assertEqual(record[field], valid)
            invalid = self.client.put('/'+table+'/'+identifier, headers=headers, json={field:valid+'x'})
            self.assertEqual(invalid.status_code, 422)
            self.assertEqual(invalid.json()['error']['code'], 'VALIDATION_ERROR')
            self.assertEqual(self.client.get('/'+table+'/'+identifier, headers=headers).json()[field], valid)
            # A lowered future policy must not break GET or an unrelated partial PUT.
            with patch('app.text_limits.DESCRIPTION_MAX_LENGTH', 2):
                read = self.client.get('/'+table+'/'+identifier, headers=headers)
                self.assertEqual(read.status_code, 200);self.assertEqual(read.json()[field], valid)
                display = next(key for key in base if key.startswith('display_name_'))
                updated = self.client.put('/'+table+'/'+identifier, headers=headers, json={display:'Renamed historical record'})
                self.assertEqual(updated.status_code, 200);self.assertEqual(updated.json()[field], valid)
            cleared = self.client.put('/'+table+'/'+identifier, headers=headers, json={field:None})
            self.assertEqual(cleared.status_code, 200);self.assertIsNone(cleared.json()[field])

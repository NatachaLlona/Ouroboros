"""Read-time page enrichment, snapshot consistency and bounded data SELECTs."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
import unittest
from unittest.mock import patch

from psycopg import Cursor, IsolationLevel
from pydantic import ValidationError
import test_api as api
import test_catalogue_api as legacy
from app.catalogue_repository import CatalogueRepository
from app.creation import CREATION_EXAMPLES
from app.database import connect
from app.schemas.catalogue import RESOURCES
from app.schemas.relationships import RELATIONSHIPS, SUMMARY_FIELDS


class RelationshipListUnitTests(unittest.TestCase):
    setUpClass = classmethod(api.APITests.setUpClass.__func__)
    setUp = api.APITests.setUp

    def test_collection_only_schemas_and_unchanged_write_inputs(self):
        schema = self.app.openapi()
        for table, resource in RESOURCES.items():
            operation = schema['paths']['/' + table]
            page = operation['get']['responses']['200']['content']['application/json']['schema']['$ref'].split('/')[-1]
            item = schema['components']['schemas'][page]['properties']['items']['items']['$ref'].split('/')[-1]
            self.assertEqual(item, resource.list_record.__name__)
            self.assertEqual('references' in resource.list_record.model_fields, table in RELATIONSHIPS)
            self.assertNotIn('references', resource.record.model_fields)
            self.assertNotIn('references', resource.create.model_fields)
            self.assertNotIn('references', resource.update.model_fields)
            self.assertNotIn('references', resource.query.model_fields)
            if table in RELATIONSHIPS:
                self.assertTrue(schema['components']['schemas'][item]['properties']['references']['readOnly'])
                for model in (resource.create, resource.update):
                    with self.assertRaises(ValidationError):
                        model.model_validate({**CREATION_EXAMPLES[table], 'references': {}})
        fields = RESOURCES['tag_category_relationships'].list_record.model_fields['references'].annotation.model_fields
        self.assertEqual(set(fields), {'tag', 'tag_category'})
        self.assertEqual(set(SUMMARY_FIELDS['tags']), {'id_tags', 'tag_name', 'display_name_tags', 'fantasy_name_tags'})


@unittest.skipUnless(os.environ.get('FOUNDATION_RUN_INTEGRATION') == '1', 'Requires owned disposable Docker integration')
class RelationshipListIntegrationTests(unittest.TestCase):
    setUpClass = classmethod(legacy.CatalogueAPITests.setUpClass.__func__)
    cleanup = classmethod(legacy.CatalogueAPITests.cleanup.__func__)
    setUp = legacy.CatalogueAPITests.setUp
    call = legacy.CatalogueAPITests.call
    create = legacy.CatalogueAPITests.create
    graph = legacy.CatalogueAPITests.graph

    def measured(self, table, **params):
        """Observe only the repository's data connection, excluding auth/audit setup."""
        observed = []
        acquire = self.provider.connection
        original = CatalogueRepository.page
        test = self

        class RecordingCursor(Cursor):
            def execute(self, query, params=None, **kwargs):
                observed.append((query.as_string(self.connection) if hasattr(query, 'as_string') else str(query), params))
                return super().execute(query, params, **kwargs)

        @contextmanager
        def recording_connection():
            with acquire() as connection:
                connection.cursor_factory = RecordingCursor
                yield connection

        def page(repository, selection):
            with patch.object(test.provider, 'connection', recording_connection):
                return original(repository, selection)

        with patch.object(CatalogueRepository, 'page', page):
            response = self.call('GET', '/' + table, params=params)
        return response, observed

    def test_all_relationship_projections_permissions_and_read_only_evidence(self):
        rows = self.graph()
        classification = rows['work_classifications']['id_work_classifications']
        self.call('PUT', '/watchlist_entries/' + rows['watchlist_entries']['id_watchlist_entries'],
                  json={'id_work_classifications_predicted': classification})
        self.call('PUT', '/watch_history/' + rows['watch_history']['id_watch_history'],
                  json={'id_work_classifications': classification})
        self.create('work_tags', id_works=rows['works']['id_works'],
                    id_tag_relationships=rows['tag_relationships']['id_tag_relationships'],
                    id_watch_history=rows['watch_history']['id_watch_history'])
        before = {}
        with self.provider.connection() as connection:
            for table, resource in RESOURCES.items():
                before[table] = connection.execute('SELECT * FROM public.' + table + ' ORDER BY ' + resource.key).fetchall()
        for table, references in RELATIONSHIPS.items():
            response, queries = self.measured(table)
            page = response.json()
            needed = {reference.table for reference in references
                      if any(row[reference.field] is not None for row in page['items'])}
            self.assertEqual(len(queries), 1 + len(needed))
            self.assertTrue(all(query.lstrip().startswith(('SELECT', 'WITH')) for query, _ in queries))
            for item in page['items']:
                self.assertEqual(set(item['references']), {reference.alias for reference in references})
                canonical = self.call('GET', '/' + table + '/' + item[RESOURCES[table].key]).json()
                self.assertEqual({key: value for key, value in item.items() if key != 'references'}, canonical)
                for reference in references:
                    summary = item['references'][reference.alias]
                    if item[reference.field] is None:
                        self.assertIsNone(summary)
                        continue
                    actual = self.call('GET', '/' + reference.table + '/' + item[reference.field]).json()
                    self.assertEqual(summary, {field: actual[field] for field in SUMMARY_FIELDS[reference.table]})
                    self.assertNotIn('references', summary)
                    self.assertNotIn('presentation', summary)
            evidence = self.call('GET', '/api_audit_logs', params={'interaction_id': response.headers['X-Interaction-ID']}).json()['items'][0]
            self.assertEqual(evidence['mutation_count'], 0)
            self.assertEqual(evidence['business_outcome'], 'read_only')
            self.call('GET', '/' + table, role='standard', expected=403)
            self.call('GET', '/' + table, role='administrator')
        with self.provider.connection() as connection:
            for table, resource in RESOURCES.items():
                self.assertEqual(connection.execute('SELECT * FROM public.' + table + ' ORDER BY ' + resource.key).fetchall(), before[table])
        # Existing ID-only create/update behavior and responses remain intact.
        body = {'id_tags_source': rows['tags']['id_tags'], 'id_tags_target': self.target['id_tags']}
        created = self.create('tag_relationships', **body)
        self.assertNotIn('references', created)
        updated = self.call('PUT', '/tag_relationships/' + created['id_tag_relationships'], json=body).json()
        self.assertNotIn('references', updated)

    def test_page_ids_count_order_names_renames_and_constant_query_counts(self):
        tags = self.call('POST', '/tags', expected=201, json=[{
            'tag_name': 'tag_' + str(index), 'display_name_tags': 'Tag ' + str(index)} for index in range(25)]).json()['items']
        categories = self.call('POST', '/tag_categories', expected=201, json=[{
            'tag_category_name': 'category_' + str(index), 'display_name_tag_categories': 'Category ' + str(index)} for index in range(3)]).json()['items']
        links = self.call('POST', '/tag_category_relationships', expected=201, json=[{
            'id_tags': tag['id_tags'], 'id_tag_categories': categories[index % 3]['id_tag_categories']}
            for index, tag in enumerate(tags)]).json()['items']
        unused_tag = self.create('tags', tag_name='unused', display_name_tags='Unused')
        unused_category = self.create('tag_categories', tag_category_name='unused', display_name_tag_categories='Unused')
        for size, page_number, direction in ((10, 1, 'asc'), (10, 2, 'desc'), (50, 1, 'asc')):
            response, queries = self.measured('tag_category_relationships', page_size=size, page=page_number, order_direction=direction)
            result = response.json()
            self.assertEqual(result['count'], 25)
            self.assertEqual((result['page'], result['page_size']), (page_number, size))
            expected = links if direction == 'asc' else list(reversed(links))
            expected = expected[(page_number-1)*size:page_number*size]
            self.assertEqual([row['id_tag_category_relationships'] for row in result['items']], [row['id_tag_category_relationships'] for row in expected])
            self.assertEqual(len(queries), 3)
            tag_ids, category_ids = queries[1][1][0], queries[2][1][0]
            self.assertEqual(set(tag_ids), {row['id_tags'] for row in expected})
            self.assertEqual(set(category_ids), {row['id_tag_categories'] for row in expected})
            self.assertNotIn(unused_tag['id_tags'], tag_ids)
            self.assertNotIn(unused_category['id_tag_categories'], category_ids)
        filtered, queries = self.measured('tag_category_relationships', id_tags=tags[0]['id_tags'])
        self.assertEqual(filtered.json()['count'], 1)
        self.assertEqual(len(queries), 3)
        for criteria, count in (({'page': 10}, 25), ({'id_tags': unused_tag['id_tags']}, 0)):
            empty, queries = self.measured('tag_category_relationships', **criteria)
            self.assertEqual(empty.json()['items'], [])
            self.assertEqual(empty.json()['count'], count)
            self.assertEqual(len(queries), 1)
        relationships = self.call('POST', '/tag_relationships', expected=201, json=[{
            'id_tags_source': tags[index % 2]['id_tags'], 'id_tags_target': tags[2 + index % 3]['id_tags']}
            for index in range(25)]).json()['items']
        response, queries = self.measured('tag_relationships', page_size=10)
        self.assertEqual(len(queries), 2)
        expected_ids = {row[field] for row in relationships[:10] for field in ('id_tags_source', 'id_tags_target')}
        self.assertEqual(set(queries[1][1][0]), expected_ids)
        for row in response.json()['items']:
            self.assertEqual(row['references']['source_tag']['id_tags'], row['id_tags_source'])
            self.assertEqual(row['references']['target_tag']['id_tags'], row['id_tags_target'])
            self.assertNotEqual(row['references']['source_tag']['tag_name'], row['references']['target_tag']['tag_name'])
        self.call('PUT', '/tags/' + tags[0]['id_tags'], json={'tag_name': 'renamed_tag', 'display_name_tags': 'Renamed tag'})
        self.call('PUT', '/tag_categories/' + categories[0]['id_tag_categories'], json={'tag_category_name': 'renamed_category', 'display_name_tag_categories': 'Renamed category'})
        row = self.call('GET', '/tag_category_relationships', params={'id_tags': tags[0]['id_tags']}).json()['items'][0]
        self.assertEqual(row['references']['tag']['tag_name'], 'renamed_tag')
        self.assertEqual(row['references']['tag']['display_name_tags'], 'Renamed tag')
        self.assertEqual(row['references']['tag_category']['tag_category_name'], 'renamed_category')
        self.assertEqual(row['references']['tag_category']['display_name_tag_categories'], 'Renamed category')
        row = self.call('GET', '/tag_relationships', params={'id_tags_source': tags[0]['id_tags']}).json()['items'][0]
        self.assertEqual(row['references']['source_tag']['tag_name'], 'renamed_tag')

    def test_consistent_snapshot_across_page_and_reference_batches(self):
        tag = self.create('tags', tag_name='before_tag', display_name_tags='Before tag')
        category = self.create('tag_categories', tag_category_name='before_category', display_name_tag_categories='Before category')
        link = self.create('tag_category_relationships', id_tags=tag['id_tags'], id_tag_categories=category['id_tag_categories'])
        from app.collection_queries import select_page
        def rename():
            # Exact disposable database owned by this fixture; a separate committed writer.
            with connect(self.database_config, self.master) as connection:
                connection.execute("UPDATE public.tags SET tag_name='after_tag', display_name_tags='After tag' WHERE id_tags=%s", (tag['id_tags'],))
                connection.execute("UPDATE public.tag_categories SET tag_category_name='after_category', display_name_tag_categories='After category' WHERE id_tag_categories=%s", (category['id_tag_categories'],))
        def concurrent_page(connection, *args):
            result = select_page(connection, *args)
            self.assertEqual(connection.isolation_level, IsolationLevel.REPEATABLE_READ)
            self.assertTrue(connection.read_only)
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(rename).result(timeout=10)
            return result
        with patch('app.catalogue_repository.select_page', concurrent_page):
            response = self.call('GET', '/tag_category_relationships')
        row = response.json()['items'][0]
        self.assertEqual(row['id_tag_category_relationships'], link['id_tag_category_relationships'])
        self.assertEqual(row['references']['tag']['tag_name'], 'before_tag')
        self.assertEqual(row['references']['tag_category']['tag_category_name'], 'before_category')
        current = self.call('GET', '/tag_category_relationships').json()['items'][0]
        self.assertEqual(current['references']['tag']['tag_name'], 'after_tag')
        self.assertEqual(current['references']['tag_category']['tag_category_name'], 'after_category')

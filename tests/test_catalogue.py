"""Catalogue integrity against a uniquely owned disposable PostgreSQL cluster."""
import os
from pathlib import Path
import secrets
import shutil
import socket
import tempfile
import unittest
import uuid

from psycopg import errors, sql

from app.config import PROJECT_ROOT
from app.credentials import write_secret
from app.database import (check_docker, compose_command, compose_environment,
                          connect, run_command, start_postgres)
from app.migrate import migrate


TABLES = {
    'works': ('WK', 'Obras'),
    'platforms': ('PL', 'Plataformas'),
    'work_availabilities': ('AV', 'Disponibilidade de obras por plataformas'),
    'tags': ('TG', 'Tags'),
    'tag_categories': ('TC', 'Categorias de tags'),
    'tag_category_relationships': ('CR', 'Vínculos entre tags e categorias'),
    'tag_relationships': ('TR', 'Relacionamentos entre tags'),
    'work_tags': ('WT', 'Vínculos entre obras e tags'),
    'work_classifications': ('WC', 'Classificações de obras'),
    'watchlist_entries': ('WS', 'To Be Watched'),
    'watch_history': ('WH', 'Watched'),
}


@unittest.skipUnless(os.environ.get('FOUNDATION_RUN_INTEGRATION') == '1',
                     'Requires explicitly enabled disposable Docker integration')
class CatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Allocate exact UUID resources; register cleanup before preparation."""
        check_docker()
        cls.root = Path(tempfile.mkdtemp(prefix='ouroboros-catalogue-'))
        cls.project = 'ouroboros-catalogue-' + uuid.uuid4().hex
        shutil.copy(PROJECT_ROOT / 'compose.yaml', cls.root)
        shutil.copytree(PROJECT_ROOT / 'sql', cls.root / 'sql')
        with socket.socket() as available:
            available.bind(('127.0.0.1', 0))
            port = available.getsockname()[1]
        cls.database = dict(name='catalogue_test', user='catalogue_master', port=port,
                            startup_timeout=240, connect_timeout=10, statement_timeout=30)
        cls.password = secrets.token_urlsafe(32)
        cls.secret = write_secret(cls.password, cls.root)
        cls.env = compose_environment(cls.database, cls.secret)
        cls.command = compose_command(cls.root, cls.project)
        cls.addClassCleanup(cls.cleanup_cluster)
        start_postgres(cls.database, cls.secret, cls.root, cls.project)
        with connect(cls.database, cls.password) as connection:
            migrate(connection, cls.root)

    @classmethod
    def cleanup_cluster(cls):
        """Remove only the resources allocated by this fixture, including its volume."""
        run_command(cls.command + ['down', '--volumes'], 60, cls.env)
        shutil.rmtree(cls.root)
        cls.password = None

    def setUp(self):
        self.connection = connect(self.database, self.password)
        self.addCleanup(self.connection.close)
        self.addCleanup(self.connection.rollback)

    def query(self, statement, values=()):
        """Execute in the test transaction; return rows when available."""
        with self.connection.cursor() as cursor:
            cursor.execute(statement, values)
            return cursor.fetchall() if cursor.description else None

    def insert(self, table, **values):
        """Insert only domain values and read back the database-generated ID."""
        if values:
            statement = sql.SQL('INSERT INTO public.{} ({}) VALUES ({}) RETURNING {}').format(
                sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, values)),
                sql.SQL(',').join(sql.Placeholder() for _ in values), sql.Identifier('id_' + table))
        else:
            statement = sql.SQL('INSERT INTO public.{} DEFAULT VALUES RETURNING {}').format(
                sql.Identifier(table), sql.Identifier('id_' + table))
        return self.query(statement, tuple(values.values()))[0][0]

    def reject(self, exception, operation, *args, **kwargs):
        """Contain each expected integrity violation in a savepoint."""
        with self.assertRaises(exception):
            with self.connection.transaction():
                operation(*args, **kwargs)

    def graph(self):
        """Create independent works and a reusable association for consistency probes."""
        first = self.insert('works', title='El dragón 🐉', title_language='es')
        other = self.insert('works', title='El dragón 🐉', title_language='es')
        platform = self.insert('platforms', platform_name='Library', platform_is_paid=False,
                               platform_is_episodes=False, platform_is_duration_time=False)
        availability = self.insert('work_availabilities', id_works=first, id_platforms=platform)
        tag = self.insert('tags', tag_name='romantic_partner', display_name_tags='Romance 💕')
        target = self.insert('tags', tag_name='support_without_dependence', display_name_tags='Support')
        relationship = self.insert('tag_relationships', id_tags_source=tag, id_tags_target=target)
        category = self.insert('tag_categories', tag_category_name='relationships', display_name_tag_categories='Vínculos')
        classification = self.insert('work_classifications', work_classification_name='favorite',
                                     display_name_work_classifications='🏆 PQP')
        return first, other, platform, availability, tag, target, relationship, category, classification

    def test_01_exact_empty_schema_and_migration_replay(self):
        names = {row[0] for row in self.query("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
        self.assertEqual(names, set(TABLES) | {'test', 'api_users', 'foundation_migrations', 'api_audit_logs'})
        domain_fields = {
            'works': 'title title_language synopsis?',
            'platforms': 'platform_name platform_is_paid platform_is_episodes platform_is_duration_time price_amount? price_currency?',
            'work_availabilities': 'id_works id_platforms duration_minutes? episode_quantity? publisher_profile? url?',
            'tags': 'tag_name display_name_tags description_tags?',
            'tag_categories': 'tag_category_name display_name_tag_categories description_tag_categories?',
            'tag_category_relationships': 'id_tags id_tag_categories',
            'tag_relationships': 'id_tags_source id_tags_target',
            'work_classifications': 'work_classification_name display_name_work_classifications description_work_classifications? tier',
            'watchlist_entries': 'id_works id_work_availabilities? id_work_classifications_predicted? observations? added_at',
            'watch_history': 'id_works id_work_availabilities? id_work_classifications? observations? watched_at?',
            'work_tags': 'id_works id_tags? id_tag_relationships? id_watchlist_entries? id_watch_history?',
        }
        for table in TABLES:
            self.assertEqual(self.query(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(table))), [(0,)])
            expected = {field.rstrip('?'): 'YES' if field.endswith('?') else 'NO'
                        for field in domain_fields[table].split()}
            expected.update({prefix + table: 'NO' for prefix in ('id_', 'sequence_', 'prefix_', 'fantasy_name_')})
            expected.update(created_at='YES', created_at_timezone='YES')
            if table == 'watchlist_entries':
                expected['added_at_timezone'] = 'YES'
            if table == 'watch_history':
                expected.update(watched_at_offset='YES', watched_at_timezone='YES')
            actual = dict(self.query("""SELECT column_name, is_nullable FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s""", (table,)))
            self.assertEqual(actual, expected)
        before = self.query('SELECT version, checksum, applied_at FROM public.foundation_migrations ORDER BY version')
        migrate(self.connection, self.root)
        self.assertEqual(self.query('SELECT version, checksum, applied_at FROM public.foundation_migrations ORDER BY version'), before)
        self.assertEqual(len(before), 10)

    def test_02_automatic_metadata_independent_sequences_and_immutability(self):
        first, other, platform, availability, tag, target, relationship, category, classification = self.graph()
        self.insert('tag_category_relationships', id_tags=tag, id_tag_categories=category)
        watchlist = self.insert('watchlist_entries', id_works=first)
        history = self.insert('watch_history', id_works=first)
        self.insert('work_tags', id_works=first, id_tags=tag)
        for table, (prefix, fantasy) in TABLES.items():
            row = self.query(sql.SQL('SELECT {}, {}, {}, {} FROM public.{} ORDER BY {} LIMIT 1').format(
                *(sql.Identifier(name + table) for name in ('id_', 'sequence_', 'prefix_', 'fantasy_name_')),
                sql.Identifier(table), sql.Identifier('sequence_' + table)))[0]
            self.assertEqual(row, (prefix + str(row[1]).zfill(7), row[1], prefix, fantasy))
            self.assertEqual(row[1], 1)
            self.reject(errors.CheckViolation, self.query,
                        sql.SQL('UPDATE public.{} SET {} = DEFAULT').format(sql.Identifier(table), sql.Identifier('sequence_' + table)))
            for column, value in [('prefix_', 'XX'), ('fantasy_name_', 'Changed')]:
                self.reject(errors.CheckViolation, self.query,
                            sql.SQL('UPDATE public.{} SET {} = %s').format(sql.Identifier(table), sql.Identifier(column + table)), (value,))
            self.reject(errors.GeneratedAlways, self.query,
                        sql.SQL('UPDATE public.{} SET {} = %s').format(sql.Identifier(table), sql.Identifier('id_' + table)), ('XX0000001',))
        self.query('UPDATE public.tags SET tag_name=%s, display_name_tags=%s WHERE id_tags=%s', ('renamed', 'New 🌟', tag))
        self.assertEqual(self.query('SELECT id_tags FROM public.tags WHERE tag_name=%s', ('renamed',)), [(tag,)])
        self.assertIsNotNone(self.query('SELECT added_at FROM public.watchlist_entries WHERE id_watchlist_entries=%s', (watchlist,))[0][0].tzinfo)
        self.assertEqual(self.query('SELECT watched_at FROM public.watch_history WHERE id_watch_history=%s', (history,)), [(None,)])

    def test_03_long_ids_gaps_and_fixed_insert_metadata(self):
        # ALTER SEQUENCE and deletion occur solely inside this fixture's UUID cluster.
        first = self.insert('works', title='First', title_language='en')
        self.query('DELETE FROM public.works WHERE id_works=%s', (first,))
        second = self.insert('works', title='Second', title_language='en')
        self.assertNotEqual(first, second)
        self.query('ALTER SEQUENCE public.works_sequence_works_seq RESTART WITH 9999999')
        self.assertEqual(self.insert('works', title='Boundary', title_language='en'), 'WK9999999')
        self.assertEqual(self.insert('works', title='Beyond', title_language='en'), 'WK10000000')
        self.assertEqual(self.insert('works', title='Beyond again', title_language='en'), 'WK10000001')
        for field, value in [('prefix_works', 'TG'), ('fantasy_name_works', 'Wrong')]:
            self.reject(errors.CheckViolation, self.insert, 'works', title='Invalid', title_language='en', **{field: value})
        self.reject(errors.GeneratedAlways, self.insert, 'works', title='Invalid', title_language='en', sequence_works=1)
        self.reject(errors.GeneratedAlways, self.insert, 'works', title='Invalid', title_language='en', id_works='WK1234567')

    def test_04_required_optional_numeric_unicode_and_long_text(self):
        for table in ['works', 'platforms', 'tags', 'tag_categories', 'tag_relationships',
                      'tag_category_relationships', 'work_availabilities', 'work_tags',
                      'work_classifications', 'watchlist_entries', 'watch_history']:
            self.reject(errors.NotNullViolation, self.insert, table)
        content = 'An English synopsis with Unicode 🐍. ' * 3000
        work = self.insert('works', title='Título 原文 🎥', title_language='pt', synopsis=content)
        self.assertEqual(self.query('SELECT title, synopsis FROM public.works WHERE id_works=%s', (work,)), [('Título 原文 🎥', content)])
        for table, technical, friendly, description in [
            ('tags', 'tag_name', 'display_name_tags', 'description_tags'),
            ('tag_categories', 'tag_category_name', 'display_name_tag_categories', 'description_tag_categories'),
            ('work_classifications', 'work_classification_name', 'display_name_work_classifications', 'description_work_classifications')]:
            record = self.insert(table, **{technical: 'valid_name_2', friendly: 'Ação 💞 + 原文', description: content})
            self.assertEqual(self.query(sql.SQL('SELECT {} FROM public.{} WHERE {}=%s').format(
                sql.Identifier(description), sql.Identifier(table), sql.Identifier('id_' + table)), (record,)), [(content,)])
            for bad in ['Invalid Name', '_start', 'double__underscore', 'trailing_', '']:
                self.reject(errors.CheckViolation, self.insert, table, **{technical: bad, friendly: 'Valid'})
        for paid in (True, False):
            for episodes in (True, False):
                for duration in (True, False):
                    platform = self.insert('platforms', platform_name='Repeated name', platform_is_paid=paid,
                                           platform_is_episodes=episodes, platform_is_duration_time=duration)
                    self.insert('work_availabilities', id_works=work, id_platforms=platform,
                                duration_minutes='12.5', episode_quantity=2)
        self.query('UPDATE public.platforms SET price_amount=12.34, price_currency=%s', ('EUR',))
        self.assertEqual(str(self.query('SELECT price_amount FROM public.platforms LIMIT 1')[0][0]), '12.34')
        for bad in ('-1', 'NaN', 'Infinity'):
            self.reject(errors.CheckViolation, self.query, 'UPDATE public.platforms SET price_amount=%s', (bad,))
        for field in ('duration_minutes', 'episode_quantity'):
            for bad in (0, -1):
                self.reject(errors.CheckViolation, self.query, sql.SQL('UPDATE public.work_availabilities SET {}=%s').format(sql.Identifier(field)), (bad,))

    def test_05_foreign_keys_same_work_and_restrictive_deletion(self):
        first, other, platform, availability, tag, target, relationship, category, classification = self.graph()
        for table, classification_field in [('watchlist_entries', 'id_work_classifications_predicted'), ('watch_history', 'id_work_classifications')]:
            self.reject(errors.ForeignKeyViolation, self.insert, table, id_works=other, id_work_availabilities=availability)
            record = self.insert(table, id_works=first, id_work_availabilities=availability, **{classification_field: classification})
            self.reject(errors.ForeignKeyViolation, self.query, sql.SQL('UPDATE public.{} SET id_works=%s').format(sql.Identifier(table)), (other,))
            origin = 'id_' + table
            self.insert('work_tags', id_works=first, id_tags=tag, **{origin: record})
            self.reject(errors.ForeignKeyViolation, self.insert, 'work_tags', id_works=other, id_tags=tag, **{origin: record})
        self.insert('tag_category_relationships', id_tags=tag, id_tag_categories=category)
        # Probe every FK from PostgreSQL's own inventory, including both halves of composites.
        self.insert('work_tags', id_works=first, id_tag_relationships=relationship)
        foreign_keys = self.query("""SELECT c.conrelid::regclass::text, a.attname
            FROM pg_constraint c CROSS JOIN LATERAL unnest(c.conkey) AS k(attnum)
            JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum
            WHERE c.contype='f' AND c.connamespace='public'::regnamespace""")
        self.assertEqual(len(foreign_keys), 21)
        for table, column in foreign_keys:
            self.reject(errors.ForeignKeyViolation, self.query, sql.SQL('UPDATE {} SET {}=%s WHERE {} IS NOT NULL').format(
                sql.Identifier(table), sql.Identifier(column), sql.Identifier(column)), ('MISSING0000001',))
        for table in ['works', 'platforms', 'work_availabilities', 'tags', 'tag_categories',
                      'tag_relationships', 'work_classifications', 'watchlist_entries', 'watch_history']:
            self.reject(errors.ForeignKeyViolation, self.query, sql.SQL('DELETE FROM public.{}').format(sql.Identifier(table)))

    def test_06_many_to_many_ordered_relationships_and_repeated_experiences(self):
        first, other, platform, availability, tag, target, relationship, category, classification = self.graph()
        self.insert('tag_category_relationships', id_tags=tag, id_tag_categories=category)
        self.insert('tag_category_relationships', id_tags=target, id_tag_categories=category)
        second_category = self.insert('tag_categories', tag_category_name='other', display_name_tag_categories='Other')
        self.insert('tag_category_relationships', id_tags=tag, id_tag_categories=second_category)
        self.reject(errors.UniqueViolation, self.insert, 'tag_category_relationships', id_tags=tag, id_tag_categories=category)
        inverse = self.insert('tag_relationships', id_tags_source=target, id_tags_target=tag)
        self.assertNotEqual(inverse, relationship)
        self.assertEqual(self.query('SELECT count(*) FROM public.work_tags'), [(0,)])
        for _ in range(2):
            self.insert('work_availabilities', id_works=first, id_platforms=platform)
            watchlist = self.insert('watchlist_entries', id_works=first, id_work_availabilities=availability)
            history = self.insert('watch_history', id_works=first, id_work_availabilities=availability,
                                  observations='Independent experience', watched_at='2020-01-01T12:00:00+01:00')
            for origin in ({}, {'id_watchlist_entries': watchlist}, {'id_watch_history': history}):
                self.insert('work_tags', id_works=first, id_tags=tag, **origin)
                self.insert('work_tags', id_works=first, id_tag_relationships=relationship, **origin)
        self.assertEqual(self.query('SELECT count(*) FROM public.work_tags'), [(12,)])
        self.reject(errors.CheckViolation, self.insert, 'work_tags', id_works=first)
        self.reject(errors.CheckViolation, self.insert, 'work_tags', id_works=first, id_tags=tag, id_tag_relationships=relationship)
        self.reject(errors.CheckViolation, self.insert, 'work_tags', id_works=first, id_tags=tag,
                    id_watchlist_entries=watchlist, id_watch_history=history)
        self.reject(errors.CheckViolation, self.query, 'UPDATE public.work_tags SET id_tags=NULL, id_tag_relationships=NULL')

    def test_07_restart_preserves_records_and_checksums(self):
        work = self.insert('works', title='Persistent work', title_language='en')
        before = self.query('SELECT version, checksum, applied_at FROM public.foundation_migrations ORDER BY version')
        self.connection.commit()
        run_command(self.command + ['stop', 'postgres'], 30, self.env)
        start_postgres(self.database, self.secret, self.root, self.project)
        with connect(self.database, self.password) as connection:
            migrate(connection, self.root)
            with connection.cursor() as cursor:
                cursor.execute('SELECT title FROM public.works WHERE id_works=%s', (work,))
                self.assertEqual(cursor.fetchone(), ('Persistent work',))
                cursor.execute('SELECT version, checksum, applied_at FROM public.foundation_migrations ORDER BY version')
                self.assertEqual(cursor.fetchall(), before)

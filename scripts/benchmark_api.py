"""Measure real HTTP workloads using only UUID-owned synthetic infrastructure.

Never loads local application configuration or local secrets. Run from the
repository virtual environment; Docker must be available. Reports contain no
passwords, tokens, connection strings, row bodies, or host account identities.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from psycopg import sql

from app.api_credentials import PASSWORD_HASHER
from app.api_users import APIUserStore
from app.auth import AuthService
from app.config import PROJECT_ROOT
from app.credentials import write_secret
from app.database import (Database, check_docker, compose_command,
                          compose_environment, connect, run_command, start_postgres)
from app.logger import ApplicationLogger
from app.main import create_app
from app.migrate import migrate


class SilentConsole(io.TextIOBase):
    """Keep real file logging enabled without printing request data to console."""
    def write(self, text):
        return len(text)

    def isatty(self):
        return False


def percentile(values, fraction):
    """Linearly interpolate percentiles; samples include all HTTP outcomes."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    left = int(position)
    right = min(left + 1, len(ordered) - 1)
    return round(ordered[left] + (ordered[right] - ordered[left]) * (position - left), 3)


class HTTPWorkload:
    """Use fresh loopback HTTP connections, with bounded timeouts and safe output."""
    def __init__(self, base_url):
        self.base_url, self.token = base_url, None

    def call(self, method, path, body=None, *, expected=200, form=False):
        headers = {}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        if body is None:
            data = None
        elif form:
            data = urlencode(body).encode('utf-8')
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            data = json.dumps(body, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=90) as response:
                status, content = response.status, response.read()
        except HTTPError as error:
            status, content = error.code, error.read()
        except (URLError, TimeoutError, ConnectionError, OSError):
            status, content = 0, b''
        elapsed = (time.perf_counter() - started) * 1000
        return elapsed, status, status == expected, content

    def measure(self, name, concurrency, count, operation):
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as workers:
            results = list(workers.map(operation, range(count)))
        elapsed = time.perf_counter() - started
        latencies = [row[0] for row in results]
        statuses = {}
        for row in results:
            statuses[str(row[1])] = statuses.get(str(row[1]), 0) + 1
        errors = sum(not row[2] for row in results)
        report = dict(name=name, concurrency=concurrency, requests=count,
            elapsed_seconds=round(elapsed, 3), p50_ms=percentile(latencies, .50),
            p95_ms=percentile(latencies, .95), minimum_ms=round(min(latencies), 3),
            maximum_ms=round(max(latencies), 3), requests_per_second=round(count / elapsed, 3),
            errors=errors, error_rate=round(errors / count, 6), statuses=statuses)
        print(json.dumps(report), flush=True)
        return report


@contextmanager
def isolated_cluster():
    """Create/clean an exact UUID project, volume, directory and random credentials."""
    check_docker()
    root = Path(tempfile.mkdtemp(prefix='ouroboros-benchmark-')).resolve()
    project = 'ouroboros-benchmark-' + uuid.uuid4().hex
    command, environment = None, None
    provider, logger, server, worker, listener, auth = None, None, None, None, None, None
    try:
        shutil.copy(PROJECT_ROOT / 'compose.yaml', root)
        shutil.copytree(PROJECT_ROOT / 'sql', root / 'sql')
        config = json.loads((PROJECT_ROOT / '.app.config.example').read_text(encoding='utf-8'))
        with socket.socket() as available:
            available.bind(('127.0.0.1', 0))
            database_port = available.getsockname()[1]
        database = {**config['database'], 'name': 'benchmark', 'user': 'benchmark_master',
                    'port': database_port, 'startup_timeout': 240,
                    'max_connections': 8, 'connection_acquire_timeout': 5}
        password = secrets.token_urlsafe(32)
        secret_file = write_secret(password, root)
        command = compose_command(root, project)
        environment = compose_environment(database, secret_file)
        start_postgres(database, secret_file, root, project)
        with connect(database, password) as connection:
            migrate(connection, root)
        provider = Database(database, password)
        users = APIUserStore(provider)
        api_password = secrets.token_urlsafe(24)
        users.create('benchmark_administrator', PASSWORD_HASHER.hash(api_password), role='administrator')
        auth = AuthService(config['auth'], secrets.token_urlsafe(64), users)
        config['logging']['level'] = 'DEBUG'
        logger = ApplicationLogger(config['logging'], root=root, stream=SilentConsole())
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(128)
        server = uvicorn.Server(uvicorn.Config(create_app(config, provider, auth, logger),
            host='127.0.0.1', port=listener.getsockname()[1], log_config=None,
            access_log=False, workers=1))
        worker = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        worker.start()
        deadline = time.monotonic() + 30
        while not server.started and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        if not server.started:
            raise RuntimeError('Isolated HTTP server did not start')
        workload = HTTPWorkload('http://127.0.0.1:' + str(listener.getsockname()[1]))
        token = workload.call('POST', '/token', {'username': 'benchmark_administrator',
            'password': api_password}, form=True)
        if not token[2]:
            raise RuntimeError('Isolated authentication setup failed')
        workload.token = json.loads(token[3])['access_token']
        yield provider, workload, logger, root
    finally:
        if server:
            server.should_exit = True
        if worker:
            worker.join(timeout=30)
            if worker.is_alive():
                raise RuntimeError('Isolated HTTP server did not stop; cleanup requires attention')
        if listener:
            listener.close()
        if auth:
            auth.close()
        if provider:
            provider.close()
        if logger:
            logger.close()
        if command is not None:
            # The command retains the exact UUID project and directory allocated
            # above. It cannot select the normal Ouroboros or Foundation project.
            run_command(command + ['down', '--volumes', '--remove-orphans'], 60, environment)
        temporary_root = Path(tempfile.gettempdir()).resolve()
        if root.parent != temporary_root or not root.name.startswith('ouroboros-benchmark-'):
            raise RuntimeError('Unexpected benchmark directory; refusing recursive cleanup')
        shutil.rmtree(root)


def seed(provider, rows, classifications):
    """Seed synthetic data through trusted fixture SQL before measured HTTP work."""
    with provider.connection() as connection, connection.cursor() as cursor:
        cursor.execute("""INSERT INTO public.works (title,title_language,synopsis)
            SELECT 'Benchmark work ' || n, 'en', repeat('Synthetic synopsis. ',64)
            FROM generate_series(1,%s) AS n""", (rows,))
        cursor.execute("""INSERT INTO public.test (value)
            SELECT 'Benchmark value ' || n FROM generate_series(1,%s) AS n""", (rows,))
        for number in range(1, classifications + 1):
            cursor.execute('''INSERT INTO public.work_classifications
                (work_classification_name,display_name_work_classifications,tier)
                VALUES (%s,%s,%s)''', ('benchmark_' + str(number), 'Benchmark ' + str(number), number))
        cursor.execute('ANALYZE public.works')
        cursor.execute('ANALYZE public.test')
        cursor.execute('ANALYZE public.work_classifications')
        cursor.execute('SELECT id_works FROM public.works ORDER BY sequence_works LIMIT 16')
        works = [row[0] for row in cursor.fetchall()]
        cursor.execute('SELECT id FROM public.test ORDER BY id LIMIT 16')
        tests = [row[0] for row in cursor.fetchall()]
        cursor.execute('SELECT id_work_classifications FROM public.work_classifications ORDER BY tier LIMIT 16')
        tiers = [row[0] for row in cursor.fetchall()]
    return works, tests, tiers


def plans_and_storage(provider):
    """Collect safe synthetic EXPLAIN ANALYZE plans and storage totals."""
    result = {}
    with provider.connection() as connection, connection.cursor() as cursor:
        from app.collection_queries import template
        from app.ordering import clause
        from app.schemas.catalogue import RESOURCES
        resource = RESOURCES['works']
        for name, predicate, parameters in (
            ('works_default_page', sql.SQL('TRUE'), (50, 0)),
            ('works_pattern_page', sql.SQL('title ILIKE %s'), ('%500%', 50, 0)),
            ('works_deep_page', sql.SQL('TRUE'), (50, 4950)),
        ):
            statement = template('catalogue_page.sql').format(
                columns=sql.SQL(', ').join(map(sql.Identifier, resource.columns)), table=sql.Identifier('works'),
                where=predicate, ordering=clause(resource.columns, 'sequence_works', 'asc', resource.key),
                page_columns=sql.SQL(', ').join(sql.Identifier('p', name) for name in resource.columns),
                page_ordering=clause(resource.columns, 'sequence_works', 'asc', resource.key, 'p'))
            cursor.execute(sql.SQL('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ') + statement, parameters)
            result[name] = cursor.fetchone()[0][0]
            # Compare both formulations on the same owned synthetic dataset.
            # Both retain the single SQL statement/snapshot and identical Params.
            comparison = {}
            for variant in ('MATERIALIZED','NOT MATERIALIZED'):
                query = statement.as_string(connection).replace('AS NOT MATERIALIZED (','AS ' + variant + ' (').replace('AS MATERIALIZED (','AS ' + variant + ' (')
                for _ in range(2):
                    cursor.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + query, parameters)
                    comparison[variant] = cursor.fetchone()[0][0]
            result[name + '_comparison'] = comparison
        cursor.execute('''SELECT count(*),sum(pg_column_size(a)),pg_total_relation_size('public.api_audit_logs'),
            sum(mutation_count), count(*) FILTER (WHERE finished_at IS NULL)
            FROM public.api_audit_logs a''')
        count, logical, physical, mutations, unfinished = cursor.fetchone()
        result['audit_storage'] = dict(rows=count, logical_row_bytes=int(logical or 0),
            table_and_index_bytes=physical, mutation_events=int(mutations or 0), unfinished_rows=unfinished)
        cursor.execute('''SELECT tablename,indexname,indexdef FROM pg_indexes
            WHERE schemaname='public' ORDER BY tablename,indexname''')
        result['indexes'] = [dict(zip(('table', 'index', 'definition'), row)) for row in cursor.fetchall()]
        cursor.execute("SELECT version(), current_setting('shared_buffers'), current_setting('max_connections')")
        version, buffers, connections = cursor.fetchone()
        result['postgresql'] = dict(version=version, shared_buffers=buffers, max_connections=int(connections))
        cursor.execute('SELECT count(*),count(DISTINCT tier),min(tier),max(tier) FROM public.work_classifications')
        count, unique, smallest, largest = cursor.fetchone()
        result['tier_integrity'] = dict(rows=count, distinct_tiers=unique, minimum=smallest, maximum=largest,
            contiguous=count == unique == largest and smallest == 1)
    return result


def benchmark(arguments):
    report = dict(format_version=1, measured_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        environment=dict(os=platform.platform(), python=platform.python_version(), logical_cpu_count=os.cpu_count(),
            packages={name: importlib.metadata.version(name) for name in ('fastapi','uvicorn','psycopg','pydantic','anyio')},
            server_workers=1, thread_pool_slots=40, database_capacity=8,
            database_acquire_timeout_seconds=5, logging_level='DEBUG', transport='real loopback HTTP; fresh connection per request'),
        dataset=dict(test_rows=arguments.rows, work_rows=arguments.rows, classifications=arguments.classifications,
            work_synopsis_bytes=len('Synthetic synopsis. ' * 64)), workloads=[])
    with isolated_cluster() as (provider, client, logger, root):
        works, tests, tiers = seed(provider, arguments.rows, arguments.classifications)
        # Warm up imports, DNS-free loopback sockets, DB/catalogue and log paths.
        for _ in range(3):
            if not client.call('GET', '/works?page_size=10')[2]:
                raise RuntimeError('Benchmark warmup failed')
        record = lambda name, concurrency, count, operation: report['workloads'].append(
            client.measure(name, concurrency, count, operation))
        for concurrency in (1, 8):
            record('works_first_page', concurrency, arguments.requests,
                lambda _: client.call('GET', '/works?page_size=50'))
        record('works_pattern_page', 8, arguments.requests,
            lambda _: client.call('GET', '/works?' + urlencode({'title':'%500%','page_size':50})))
        record('works_deep_page', 8, arguments.requests,
            lambda _: client.call('GET', '/works?page_size=50&page=' + str(max(1, arguments.rows // 50))))
        record('works_by_id', 8, arguments.requests,
            lambda i: client.call('GET', '/works/' + works[i % len(works)]))
        record('test_individual_update', 8, arguments.requests,
            lambda i: client.call('PUT', '/test/' + str(tests[i % len(tests)]), {'value':'Benchmark updated ' + str(i)}))
        record('catalogue_individual_update', 8, arguments.requests,
            lambda i: client.call('PUT', '/works/' + works[i % len(works)], {'title':'Benchmark revised ' + str(i)}))
        record('tier_move', 8, arguments.requests,
            lambda i: client.call('PUT', '/work_classifications/' + tiers[i % len(tiers)],
                {'tier': 1 if i % 2 else arguments.classifications}))
        def mixed(i):
            if i % 3 == 0:
                return client.call('PUT', '/work_classifications/' + tiers[i % len(tiers)], {'tier':1})
            if i % 3 == 1:
                return client.call('PUT', '/works/' + works[i % len(works)], {'title':'Benchmark mixed ' + str(i)})
            return client.call('PUT', '/test/' + str(tests[i % len(tests)]), {'value':'Benchmark mixed ' + str(i)})
        record('mixed_writes', 16, arguments.requests, mixed)
        record('bulk_preview_all_works', 8, min(16, arguments.requests),
            lambda _: client.call('PUT', '/works?dry_run=true', {'title_language':'en'}))
        record('bulk_update_all_works', 1, 1,
            lambda _: client.call('PUT', '/works?confirm=true', {'title_language':'en'}))
        record('bulk_and_individual_contention', 8, 8,
            lambda i: client.call('PUT', '/works?confirm=true', {'title_language':'en'}) if i == 0 else
                client.call('PUT', '/test/' + str(tests[i % len(tests)]), {'value':'Benchmark after bulk ' + str(i)}))
        large_text = 'Synthetic Unicode 🐉 ' * 50_000
        report['dataset']['large_text_utf8_bytes'] = len(large_text.encode('utf-8'))
        record('large_text_test_update', 4, 8,
            lambda i: client.call('PUT', '/test/' + str(tests[i % len(tests)]), {'value':large_text}))
        record('audit_filtered_page', 8, arguments.requests,
            lambda _: client.call('GET', '/api_audit_logs?resource=works&page_size=50'))
        # Wait for response finalization, which happens after the last accepted
        # ASGI body and can therefore extend beyond client receive time.
        time.sleep(.25)
        report['database_review'] = plans_and_storage(provider)
        report['technical_log_bytes'] = sum(path.stat().st_size for path in root.rglob('*.log'))
    report['cleanup'] = 'Exact UUID Docker project and volume removed; temporary directory removed'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, default=5000)
    parser.add_argument('--classifications', type=int, default=100)
    parser.add_argument('--requests', type=int, default=40)
    parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'reports/performance.json')
    parser.add_argument('--plans-only', action='store_true', help='Compare pagination plans only in fresh owned storage; no HTTP load measurements.')
    arguments = parser.parse_args()
    if not 100 <= arguments.rows <= 100_000 or not 16 <= arguments.classifications <= 1000 or not 8 <= arguments.requests <= 1000:
        parser.error('Use rows 100..100000, classifications 16..1000 and requests 8..1000')
    if arguments.plans_only:
        with isolated_cluster() as (provider, client, logger, root):
            seed(provider,arguments.rows,arguments.classifications)
            report = {'dataset_rows':arguments.rows,'database_review':plans_and_storage(provider),
                      'measurement':'Same-dataset warmed EXPLAIN ANALYZE comparisons; no end-to-end latency claim'}
    else:
        report = benchmark(arguments)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Safe benchmark report written; disposable infrastructure cleanup completed.', flush=True)
    return int(any(row['errors'] for row in report.get('workloads',[])))


if __name__ == '__main__':
    raise SystemExit(main())

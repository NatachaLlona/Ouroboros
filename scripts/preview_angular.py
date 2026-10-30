"""Serve built Angular against UUID-owned disposable PostgreSQL, never normal data.

Requires FOUNDATION_RUN_INTEGRATION=1. Ctrl+C cleans up only allocated resources.
The optional private fixture is for local QA automation; it is not a report.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_catalogue_api import CatalogueAPITests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=2469)
    parser.add_argument('--fixture-file', type=Path)
    args = parser.parse_args()
    if os.environ.get('FOUNDATION_RUN_INTEGRATION') != '1':
        parser.error('Explicit disposable integration opt-in is required')
    if not (ROOT / 'frontend/dist/browser/index.html').is_file():
        parser.error('Build Angular first')
    # Check the listener before allocating anything; never stop an existing service.
    import socket
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    class Preview(CatalogueAPITests):
        pass
    instance = Preview('test_01_all_resources_crud_record_round_trips_and_deletes')
    created_fixture = None
    try:
        Preview.setUpClass()
        instance.setUp()
        config = {**instance.config, 'port': args.port,
                  'browser': {'origin': f'http://127.0.0.1:{args.port}', 'allow_loopback_http': True}}
        from app.main import create_app
        import uvicorn
        app = create_app(config, instance.provider, instance.auth, instance.logger)
        if args.fixture_file:
            # Private disposable QA credentials, never stdout/logs/reports/source.
            target = args.fixture_file.resolve()
            allowed = (ROOT / '.tmp').resolve()
            if allowed not in target.parents:
                parser.error('Fixture must be under ignored project .tmp/')
            target.parent.mkdir(parents=True, exist_ok=True)
            # Explicit optional bridge for browser QA, containing only fresh
            # disposable credentials. Never overwrite an existing private file.
            with target.open('x', encoding='utf-8') as output:
                if os.name != 'nt':
                    os.fchmod(output.fileno(), 0o600)
                output.write(json.dumps({'origin': config['browser']['origin'], 'password': instance.api_password}))
            created_fixture = target
        print(f'Disposable Angular QA ready at http://127.0.0.1:{args.port}/; Ctrl+C cleans up owned infrastructure.', flush=True)
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port, access_log=False, proxy_headers=False, log_config=None))
        stop = ROOT / '.tmp/angular-preview.stop'
        stop.unlink(missing_ok=True)
        done = threading.Event()
        def watch_stop():
            while not done.wait(.5):
                if stop.is_file():
                    server.should_exit = True
                    break
        watcher = threading.Thread(target=watch_stop, daemon=True)
        watcher.start()
        try:
            server.run()
        finally:
            done.set()
            watcher.join(timeout=2)
            stop.unlink(missing_ok=True)
    finally:
        instance.doCleanups()
        Preview.doClassCleanups()
        if created_fixture:
            created_fixture.unlink(missing_ok=True)


if __name__ == '__main__':
    main()

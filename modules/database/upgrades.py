"""Checksummed additions to the immutable Database v1 baseline."""
import hashlib
from pathlib import Path
from database.model import render
from database.settings import ConfigurationError

DIRECTORY = Path(__file__).with_name('sql') / 'upgrades'
MIGRATIONS = (('database-v1/002',DIRECTORY/'002_basic_plan.sql'),
              ('database-v1/003',DIRECTORY/'003_app_username.sql'))


def apply(connection, document):
    changed = False
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(719230820)')
        for version,source in MIGRATIONS:
            checksum = hashlib.sha256(source.read_bytes()).hexdigest()
            row = connection.execute(render('SELECT checksum FROM {foundation_migration} WHERE version=%s',document),(version,)).fetchone()
            if row:
                if row[0] != checksum:
                    raise ConfigurationError('Applied Database upgrade checksum mismatch: '+version)
                continue
            connection.execute('SET LOCAL ROLE ouroboros_owner')
            connection.execute(render(source.read_text(encoding='utf-8'),document))
            connection.execute(render('INSERT INTO {foundation_migration}(version,checksum) VALUES(%s,%s)',document),(version,checksum))
            changed = True
    return changed

"""Transactional, checksummed migrations with an application-wide database lock."""
import hashlib
from pathlib import Path

from app.config import PROJECT_ROOT
from app.database import DatabaseError


def migrate(connection, root=PROJECT_ROOT):
    migrations = Path(root) / "sql" / "migrations"
    if not (migrations / "001_create_test.sql").is_file():
        raise DatabaseError("Initial migration file is missing; restore sql/migrations/001_create_test.sql")
    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (719230817,))
                cursor.execute("""CREATE TABLE IF NOT EXISTS public.foundation_migrations (
                    version TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )""")
                for path in sorted(migrations.glob("*.sql")):
                    content = path.read_bytes()
                    checksum = hashlib.sha256(content).hexdigest()
                    cursor.execute("SELECT checksum FROM public.foundation_migrations WHERE version = %s", (path.name,))
                    previous = cursor.fetchone()
                    if previous:
                        if previous[0] != checksum:
                            raise DatabaseError("An applied migration was modified; restore its original contents and add a new migration")
                        continue
                    if path.name == '009_add_classification_tiers.sql':
                        cursor.execute('SELECT count(*),min(sequence_work_classifications),max(sequence_work_classifications) FROM public.work_classifications')
                        count, minimum, maximum = cursor.fetchone()
                        from app.logger import log_event
                        log_event('INFO', 'Classification tier backfill inspected', {
                            'record_count': count, 'sequence_min': minimum, 'sequence_max': maximum,
                            'backfill_strategy': 'preserved_sequence' if count == 0 or (minimum == 1 and maximum == count) else 'contiguous_sequence_rank'}, component='migrate')
                    cursor.execute(content.decode("utf-8"))
                    cursor.execute("INSERT INTO public.foundation_migrations (version, checksum) VALUES (%s, %s)", (path.name, checksum))
                cursor.execute("""SELECT column_name, data_type, is_nullable, is_identity, identity_generation
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'test' AND column_name IN ('id', 'value')
                    ORDER BY column_name""")
                if cursor.fetchall() != [("id", "bigint", "NO", "YES", "ALWAYS"),
                                         ("value", "text", "NO", "NO", None)]:
                    raise DatabaseError("Existing test table has an incompatible schema; no table was recreated or data deleted")
                cursor.execute("""SELECT array_agg(a.attname::text ORDER BY key.ordinality)
                    FROM pg_constraint c
                    CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS key(attnum, ordinality)
                    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = key.attnum
                    WHERE c.conrelid = 'public.test'::regclass AND c.contype = 'p'
                    GROUP BY c.oid""")
                if cursor.fetchall() != [(["id"],)]:
                    raise DatabaseError("Existing test table must have a primary key on id; no data was deleted")
                cursor.execute("""SELECT column_name, data_type, is_nullable FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='api_users' ORDER BY column_name""")
                expected = [("created_at", "timestamp with time zone", "NO"), ("credential_version", "bigint", "NO"), ("id", "bigint", "NO"),
                            ("is_active", "boolean", "NO"), ("password_hash", "text", "NO"),
                            ("role", "text", "NO"), ("scopes", "ARRAY", "NO"), ("username", "text", "NO")]
                if cursor.fetchall() != expected:
                    raise DatabaseError("Existing api_users table has an incompatible schema; no accounts were replaced")

    except DatabaseError:
        raise
    except Exception:
        raise DatabaseError("Database migration failed; changes were rolled back. Check schema compatibility and master user permissions") from None

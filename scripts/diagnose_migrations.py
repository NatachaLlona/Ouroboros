"""Compare exact migration bytes with Git/backups and optional read-only registry.

No migrations are executed, no registry records/files are changed, and saved
credentials are never read. --database requests the existing password privately.
"""
import argparse
import getpass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
VERSION = re.compile(r'^[0-9]{3}_[a-z0-9_]+\.sql$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')


def digest(content):
    return hashlib.sha256(content).hexdigest()


def facts(content):
    """Report formatting without normalizing the actual integrity checksum."""
    bom = ('utf-8' if content.startswith(b'\xef\xbb\xbf') else
           'utf-16-le' if content.startswith(b'\xff\xfe') else
           'utf-16-be' if content.startswith(b'\xfe\xff') else None)
    try:
        text = content.decode('utf-8-sig')
        normalized = digest(text.replace('\r\n', '\n').replace('\r', '\n').encode('utf-8'))
    except UnicodeError:
        normalized = None
    return {'sha256':digest(content), 'bytes':len(content), 'bom':bom,
            'crlf':content.count(b'\r\n'), 'bare_lf':content.count(b'\n')-content.count(b'\r\n'),
            'normalized_utf8_lf_sha256':normalized}


def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT, stderr=subprocess.DEVNULL)


def candidates(version, archives):
    """Collect public SQL only; never extract archives or inspect private members."""
    sources = []
    for commit in git('rev-list','--all','--','sql/migrations/'+version).decode().splitlines():
        try:
            sources.append(('git:'+commit, git('show',commit+':sql/migrations/'+version)))
        except subprocess.CalledProcessError:
            continue
    for archive in archives:
        if not archive.is_file():
            continue
        with ZipFile(archive) as handle:
            for member in handle.infolist():
                name = member.filename.replace('\\','/')
                if name.endswith('/sql/migrations/'+version) or name == 'sql/migrations/'+version:
                    if member.file_size > 2_000_000:
                        raise ValueError('Oversized migration archive member')
                    sources.append(('archive:'+str(archive)+'!'+member.filename,handle.read(member)))
    path = ROOT/'sql/migrations'/version
    if path.is_file():
        sources.append(('worktree',path.read_bytes()))
    # Explicitly marked formatting candidates are diagnostic only. A candidate is
    # never accepted by the migrator unless its raw hash equals the stored hash.
    originals = list(sources)
    for source, content in originals:
        try:
            text = content.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
        except UnicodeError:
            continue
        for newline, label in (('\n','LF'), ('\r\n','CRLF')):
            encoded = text.replace('\n',newline).encode('utf-8')
            sources.append((source+':derived-UTF8-'+label, encoded))
            sources.append((source+':derived-UTF8-BOM-'+label,b'\xef\xbb\xbf'+encoded))
    return sources


def inspect(archives, stored=None):
    report = {'branch':git('branch','--show-current').decode().strip(),
              'head':git('rev-parse','HEAD').decode().strip(),
              'registry_checked':stored is not None, 'migrations':[]}
    paths = {path.name:path for path in (ROOT/'sql/migrations').glob('*.sql')}
    for version in sorted(set(paths) | set(stored or {})):
        if not VERSION.fullmatch(version):
            raise ValueError('Unexpected migration version in registry or filesystem')
        path = paths.get(version)
        current = facts(path.read_bytes()) if path else None
        expected = stored.get(version) if stored is not None else None
        if expected is not None and not SHA256.fullmatch(expected):
            raise ValueError('Invalid checksum format in migration registry')
        unique = {}
        for source, content in candidates(version, archives):
            checksum = digest(content)
            unique.setdefault(checksum, {**facts(content), 'sources':[]})['sources'].append(source)
        row = {'version':version, 'current':current, 'stored_sha256':expected,
               'status':'NOT_VERIFIED' if stored is None else 'UNAPPLIED' if expected is None else
                        'MATCH' if current and current['sha256']==expected else 'DIVERGED',
               'candidates':list(unique.values())}
        if expected:
            original = unique.get(expected)
            row['proven_original_candidate'] = original
            row['formatting_only'] = bool(original and current and original['normalized_utf8_lf_sha256'] and
                original['normalized_utf8_lf_sha256']==current['normalized_utf8_lf_sha256'])
        report['migrations'].append(row)
    return report


def read_registry():
    from app.config import load_config
    from app.database import connect
    if not (ROOT/'.app.config').is_file():
        raise ValueError('Existing configuration is missing; diagnosis will not create it')
    config = load_config(ROOT)
    password = getpass.getpass('Existing PostgreSQL password (never saved by this tool): ')
    try:
        with connect(config['database'],password) as connection:
            with connection.transaction():
                connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                return dict(connection.execute('SELECT version,checksum FROM public.foundation_migrations ORDER BY version').fetchall())
    finally:
        password = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',action='store_true')
    parser.add_argument('--stored-checksums',type=Path,help='Previously exported public version-to-SHA256 JSON, never credentials')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/migration_integrity_diagnosis.json')
    args = parser.parse_args()
    if args.database and args.stored_checksums:
        parser.error('Choose one registry source')
    try:
        output = args.output.resolve()
        if (ROOT/'reports').resolve() not in output.parents:
            raise ValueError('Output must be inside project reports/')
        stored = read_registry() if args.database else json.loads(args.stored_checksums.read_text(encoding='utf-8')) if args.stored_checksums else None
        archives = (ROOT.parent/'Ouroboros.zip',ROOT/'reports/Ouroboros-final-review.zip')
        report = inspect(archives,stored)
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'branch':report['branch'],'head':report['head'],'registry_checked':report['registry_checked'],
            'migrations':[{'version':row['version'],'status':row['status'],'current_sha256':row['current']['sha256'] if row['current'] else None,
                'stored_sha256':row['stored_sha256'],'original_found':bool(row.get('proven_original_candidate')),
                'formatting_only':row.get('formatting_only')} for row in report['migrations']]},indent=2))
        return 2 if stored is None else 1 if any(row['status']=='DIVERGED' for row in report['migrations']) else 0
    except (Exception, KeyboardInterrupt) as error:
        # No raw driver exception, config, connection string or password output.
        print('Migration diagnosis incomplete: '+type(error).__name__)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())

"""Package public Foundation source and sanitized QA reports for review.

Run after scripts/run_checks.py. Explicit source allowlists exclude local
configuration, secrets, logs, Git history and personal Postman YAML/metadata.
The ZIP is an installation source snapshot, not a backup of existing data.
"""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main():
    """Create an ignored review ZIP without reading private runtime artifacts."""
    files = {ROOT / name for name in (
        'AGENTS.md', 'NEXTGENERATION.md', 'README.md', '.gitignore',
        '.app.config.example', 'compose.yaml', 'requirements.txt',
        'requirements-dev.txt', 'start.py', 'postman/Foundation.postman_collection.json')}
    for directory, patterns in (
        ('app', ('*.py',)), ('tests', ('*.py', '*.schema.json')),
        ('scripts', ('*.py',)), ('sql', ('*.sql',)), ('qa', ('*.json',)),
        ('docs', ('*.md',)), ('.github/workflows', ('*.yml', '*.yaml')),
    ):
        for pattern in patterns:
            files.update((ROOT / directory).rglob(pattern))
    files.update(ROOT / 'reports' / name for name in ('summary.md', 'results.json', 'junit.xml'))
    output = ROOT / 'reports/Foundation-final-review.zip'
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(files):
            if not path.is_file() or path.is_symlink():
                raise ValueError('Required public source/report missing or symlinked')
            relative = path.resolve().relative_to(ROOT)
            if '__pycache__' in relative.parts:
                continue
            archive.write(path, 'Foundation/' + relative.as_posix())
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('Review ZIP integrity check failed')
    print('Created reports/Foundation-final-review.zip from public allowlisted files')


if __name__ == '__main__':
    main()

"""Package public Ouroboros source and sanitized QA reports for review.

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
        'requirements-dev.txt', 'requirements-review.txt', 'start.py', 'postman/Ouroboros.postman_collection.json')}
    for directory, patterns in (
        ('app', ('*.py', '*.json')), ('tests', ('*.py', '*.schema.json')),
        ('scripts', ('*.py',)), ('sql', ('*.sql',)), ('qa', ('*.json',)),
        ('frontend/src', ('*.html', '*.css', '*.ts')),
        ('frontend/assets', ('*.svg',)), ('frontend/styles', ('*.css',)),
        ('frontend/scripts', ('*.mjs',)),
        ('docs', ('*.md',)), ('.github/workflows', ('*.yml', '*.yaml')),
    ):
        for pattern in patterns:
            files.update((ROOT / directory).rglob(pattern))
    files.update(ROOT / 'frontend' / name for name in (
        'package.json', 'package-lock.json', 'angular.json', 'tsconfig.json',
        'tsconfig.app.json', 'tsconfig.spec.json'))
    files.add(ROOT/'qa/UNICODE_LICENSE.txt')
    files.update(ROOT / 'reports' / name for name in ('summary.md', 'results.json', 'junit.xml'))
    for name in ('performance.json','pagination-plans.json','bandit.json','ruff.json','dependency-audit.json','dependency-dev-audit.json'):
        report = ROOT / 'reports' / name
        if report.is_file():
            files.add(report)
    output = ROOT / 'reports/Ouroboros-final-review.zip'
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(files):
            if not path.is_file() or path.is_symlink():
                raise ValueError('Required public source/report missing or symlinked')
            relative = path.resolve().relative_to(ROOT)
            if any(part in relative.parts for part in ('__pycache__', 'node_modules', '.angular', 'dist', 'out-tsc')):
                continue
            archive.write(path, 'Ouroboros/' + relative.as_posix())
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('Review ZIP integrity check failed')
    print('Created reports/Ouroboros-final-review.zip from public allowlisted files')


if __name__ == '__main__':
    main()

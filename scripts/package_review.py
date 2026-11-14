"""Package public Ouroboros source and sanitized QA reports for review.

Run after scripts/run_checks.py. Explicit source allowlists exclude local
configuration, secrets, logs, Git history and personal Postman YAML/metadata.
The ZIP is an installation source snapshot, not a backup of existing data.
"""

import sys as _sys
from pathlib import Path as _Path
_repository = _Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(_repository))
_sys.path.insert(0, str(_repository / "modules"))
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main():
    """Create an ignored review ZIP without reading private runtime artifacts."""
    files = {ROOT / name for name in (
        'AGENTS.md', 'NEXTGENERATION.md', 'README.md', '.gitignore',
        'config.example.json', 'provisioning.example.jsonc', 'compose.yaml', 'compose.basic.yaml',
        'orchestration.py', '.dockerignore', '.gitattributes',
        'requirements-dev.txt', 'requirements-review.txt', 'start.py',
        'modules/api/postman/Ouroboros.postman_collection.json',
        'modules/api/postman/Basic.postman_collection.json',
        'modules/api/postman/Basic.postman_environment.example.json')}
    for directory, patterns in (
        ('modules/api', ('*.py', '*.example.json', '*.example.jsonc', '*.txt', '*Dockerfile', '*.yaml')),
        ('modules/api/qa', ('*.json',)),
        ('modules/assistance', ('*.py', '*.example.json', '*.txt', 'Dockerfile')),
        ('shared', ('*.py', '*.json')),
        ('scripts', ('*.py',)),
        ('modules/database', ('*.py', '*.sql', '*.example.json', '*.example.jsonc', '*.txt', '*.yaml')),
        ('qa', ('*.py', '*.json')),
        ('modules/frontend/qa', ('*.py', '*.ts')),
        ('modules/frontend/src', ('*.html', '*.css', '*.ts')),
        ('modules/frontend/assets', ('*.svg',)), ('modules/frontend/styles', ('*.css',)),
        ('modules/frontend/scripts', ('*.mjs', '*.py')),
        ('docs', ('*.md',)), ('.github/workflows', ('*.yml', '*.yaml')),
    ):
        for pattern in patterns:
            files.update((ROOT / directory).rglob(pattern))
    files.update(ROOT / 'modules/frontend' / name for name in (
        'package.json', 'package-lock.json', 'angular.json', 'tsconfig.json',
        'tsconfig.app.json', 'tsconfig.spec.json', 'Dockerfile', 'nginx.conf', 'entrypoint.sh', 'config.example.json'))
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
            if path.name == 'config.json' or path.name.startswith('.env'):
                continue
            if any(part in relative.parts for part in ('__pycache__', 'node_modules', '.angular', 'dist', 'out-tsc')):
                continue
            if 'postman' in relative.parts and path not in {
                ROOT/'modules/api/postman/Ouroboros.postman_collection.json',
                ROOT/'modules/api/postman/Basic.postman_collection.json',
                ROOT/'modules/api/postman/Basic.postman_environment.example.json',
            }:
                continue
            archive.write(path, 'Ouroboros/' + relative.as_posix())
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('Review ZIP integrity check failed')
    print('Created reports/Ouroboros-final-review.zip from public allowlisted files')


if __name__ == '__main__':
    main()

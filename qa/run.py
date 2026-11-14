"""Run central or module-owned QA suites without duplicating tests."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SUITES = ('central', 'database', 'api', 'assistance', 'frontend')
PATHS = [ROOT, ROOT/'modules', ROOT/'scripts', ROOT/'qa/support', ROOT/'qa',
         *(ROOT/'modules'/name/'qa' for name in SUITES if name != 'central')]
sys.path[:0] = [str(path) for path in PATHS]
os.environ['PYTHONPATH'] = os.pathsep.join([*(str(path) for path in PATHS), os.environ.get('PYTHONPATH','')])


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=(*SUITES, 'all'), default='central')
    parser.add_argument('--pattern', default='test_*.py')
    args = parser.parse_args(arguments)
    selected = SUITES if args.suite == 'all' else (args.suite,)
    success = True
    records = []
    for name in selected:
        print('Running '+name+' QA', flush=True)
        if name == 'frontend':
            toolchain = ROOT/'.tools/node-v24.15.0-win-x64'
            environment = os.environ.copy()
            if toolchain.is_dir():
                environment['PATH'] = str(toolchain)+os.pathsep+environment.get('PATH','')
            npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm', path=environment.get('PATH'))
            if npm is None:
                print('Frontend QA requires Node.js and npm.', file=sys.stderr)
                success = False
                records.append({'suite':name,'passed':False})
                continue
            result = subprocess.run([npm, 'test'], cwd=ROOT/'modules/frontend', env=environment)
            success = result.returncode == 0 and success
            records.append({'suite':name,'passed':result.returncode == 0})
            continue
        directory = ROOT/'qa' if name == 'central' else ROOT/'modules'/name/'qa'
        suite = unittest.TestLoader().discover(str(directory), pattern=args.pattern)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        success = result.wasSuccessful() and success
        records.append({'suite':name,'passed':result.wasSuccessful(),'tests':result.testsRun,
                        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)})
    reports = ROOT/'reports'
    reports.mkdir(exist_ok=True)
    (reports/'results.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
    (reports/'summary.md').write_text('\n'.join(record['suite']+' QA '+('PASS' if record['passed'] else 'FAIL') for record in records)+'\n',encoding='utf-8')
    xml = ET.Element('testsuite',name='Ouroboros modular QA',tests=str(len(records)))
    for record in records:
        case = ET.SubElement(xml,'testcase',name=record['suite'])
        if not record['passed']:
            ET.SubElement(case,'failure',message='Suite did not pass. Reproduce with its documented QA command.')
    ET.ElementTree(xml).write(reports/'junit.xml',encoding='utf-8',xml_declaration=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())

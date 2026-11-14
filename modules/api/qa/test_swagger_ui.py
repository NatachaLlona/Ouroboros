"""Test the shipped Swagger bundle and authorization plugin with synthetic inputs."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]


class SwaggerUITests(unittest.TestCase):
    def test_authorize_flows_and_repeated_protected_requests(self):
        portable = ROOT/'.tools/node-v24.15.0-win-x64/node.exe'
        node = str(portable) if portable.is_file() else shutil.which('node')
        if node is None or not (ROOT/'modules/frontend/node_modules/jsdom').is_dir():
            self.skipTest('Swagger DOM checks require Node and the existing frontend QA dependencies')
        result = subprocess.run([node,str(Path(__file__).with_name('swagger_authorization.mjs'))],
                                cwd=ROOT,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,'Swagger DOM verification failed. Run modules/api/qa/swagger_authorization.mjs locally.')

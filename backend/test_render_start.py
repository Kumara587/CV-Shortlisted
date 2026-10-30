import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from render_start import prepare_environment

class RenderStartupTests(unittest.TestCase):
    def test_runtime_secret_files_and_same_origin_settings(self):
        values={'RENDER_EXTERNAL_HOSTNAME':'fictional-check.onrender.com','DATABASE_URL':'postgresql://fictional:fake@example.neon.tech/neondb',
            'SCREENER_STORAGE_KEY_JSON':json.dumps({'version':1,'keys':['fictional-key']}),
            'SCREENER_GEMINI_JSON':json.dumps({'provider':'gemini','synthetic_only':True,'api_key':'fictional-key'}),
            'SCREENER_AUTH_JSON':json.dumps({'google_client_id':'fake-client','smtp_password':'fake-password','app_url':'http://localhost:5173'})}
        root=None
        try:
            with patch.dict(os.environ,values,clear=True):
                root=prepare_environment()
                self.assertEqual(os.environ['CORS_ORIGINS'],'https://fictional-check.onrender.com')
                self.assertEqual(os.environ['PARSER_CONCURRENCY'],'1')
                self.assertEqual(os.environ['CLEANUP_INTERVAL_SECONDS'],'0')
                self.assertNotIn('SCREENER_STORAGE_KEY_JSON',os.environ)
                config=json.loads(Path(os.environ['AUTH_CONFIG_FILE']).read_text())
                self.assertEqual(config['smtp_password'],'fake-password')
                self.assertEqual(config['app_url'],'https://fictional-check.onrender.com')
        finally:
            if root:
                assert root.name.startswith('cv-runtime-')
                shutil.rmtree(root)

    def test_missing_or_invalid_hostname_fails_closed(self):
        for hostname in ['','https://example.com','evil.example']:
            with patch.dict(os.environ,{'RENDER_EXTERNAL_HOSTNAME':hostname},clear=True),self.assertRaises(ValueError):prepare_environment()

if __name__=='__main__':unittest.main()

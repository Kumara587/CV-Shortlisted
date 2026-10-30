import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch,MagicMock
from render_start import prepare_environment

class RenderStartupTests(unittest.TestCase):
    def test_runtime_schema_mode_does_not_execute_ddl(self):
        from postgres_store import PostgresStore
        store=PostgresStore('postgresql://fictional',cipher=object())
        raw=MagicMock()
        context=MagicMock();context.__enter__.return_value=raw
        with patch.dict(os.environ,{'SCREENER_SCHEMA_MODE':'verify-only'}),patch.object(store,'_connect',return_value=context),patch('postgres_store.verify_or_initialize'):
            store.initialize()
        self.assertEqual(raw.execute.call_count,9)
        self.assertFalse(any('CREATE' in str(call.args[0]) for call in raw.execute.call_args_list))

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

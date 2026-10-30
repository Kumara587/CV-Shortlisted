import json
from pathlib import Path
import tempfile
import unittest
from setup_google import save_client_id

class GoogleSetupTests(unittest.TestCase):
    def test_creates_config_and_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'auth.credentials.json'
            first='123456789-fictional.apps.googleusercontent.com'
            second='987654321-otherfictional.apps.googleusercontent.com'
            save_client_id(first,path)
            config=json.loads(path.read_text())
            self.assertEqual(config['app_url'],'http://127.0.0.1:5173')
            config['smtp_password']='fictional-test-value'
            path.write_text(json.dumps(config))
            save_client_id(second,path)
            updated=json.loads(path.read_text())
            self.assertEqual(updated['google_client_id'],second)
            self.assertEqual(updated['smtp_password'],'fictional-test-value')
            before=path.read_bytes()
            with self.assertRaises(ValueError):save_client_id('not-an-oauth-client',path)
            self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main()

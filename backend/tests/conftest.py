"""Every test has a separate temporary key; production secrets are never read."""
import json
import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def test_storage_key(tmp_path,monkeypatch):
    path=tmp_path/'test.keys.json'
    path.write_text(json.dumps({'version':1,'keys':[Fernet.generate_key().decode()]}))
    path.chmod(0o600)
    monkeypatch.setenv('SCREENER_KEY_FILE',str(path))

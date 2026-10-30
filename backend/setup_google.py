"""Configure only the public Google Web Client ID; preserve private SMTP settings."""
import json
import os
from pathlib import Path
import re
import secrets
from encryption import private_write


def configuration_path():
    return Path(os.getenv('AUTH_CONFIG_FILE',str(Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.config')))/'CVShortlisted'/'secrets'/'auth.credentials.json')))


def save_client_id(client_id,path=None):
    client_id=client_id.strip()
    if not re.fullmatch(r'[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com',client_id):
        raise ValueError('Enter the Web OAuth Client ID ending in .apps.googleusercontent.com, not a Gemini API key or client secret.')
    path=Path(path) if path else configuration_path()
    config=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'app_url':'http://127.0.0.1:5173'}
    if not isinstance(config,dict):raise ValueError('Existing authentication configuration is invalid; it was not replaced.')
    config['google_client_id']=client_id
    temporary=path.with_name('.google-setup-'+secrets.token_hex(12)+'.credentials.json')
    try:
        private_write(temporary,json.dumps(config).encode())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def main():
    print('Create a Google OAuth client with application type: Web application.')
    print('Authorized JavaScript origins: http://127.0.0.1:5173 and http://localhost:5173')
    print('A client secret is NOT needed for this sign-in flow.')
    try:save_client_id(input('Paste Google Web Client ID: '))
    except (ValueError,OSError):raise SystemExit('Could not save. Check the Web Client ID format and private file permissions. Existing SMTP settings were not changed.') from None
    print('Google Client ID configured. Refresh the app. Existing email/SMTP settings were preserved.')


if __name__=='__main__':main()

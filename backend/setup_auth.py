"""Create private authentication configuration without putting secrets in Git."""
import json
from getpass import getpass
from pathlib import Path
import os
import re
from encryption import private_write

def main():
    path=Path(os.getenv('AUTH_CONFIG_FILE',str(Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.config')))/'CVShortlisted'/'secrets'/'auth.credentials.json')))
    if path.exists():raise SystemExit('Auth configuration already exists. It was not overwritten. Edit the existing private file to change settings.')
    config={'app_url':input('Frontend origin [http://127.0.0.1:5173]: ').strip() or 'http://127.0.0.1:5173'}
    client=input('Google Web OAuth client ID (Enter to skip): ').strip()
    if client:
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.apps\.googleusercontent\.com',client):raise SystemExit('Invalid Google Web Client ID format; nothing saved.')
        config['google_client_id']=client
    host=input('SMTP hostname (Enter to skip): ').strip()
    if host:
        config.update(smtp_host=host,smtp_port=int(input('SMTP port [587]: ') or '587'),smtp_from=input('From email address: ').strip(),smtp_username=input('SMTP username: ').strip(),smtp_password=getpass('SMTP password/app password (hidden): '))
    private_write(path,json.dumps(config).encode())
    print('Private auth configuration saved. Google/SMTP secrets were not printed. Refresh the app after setup.')

if __name__=='__main__':main()

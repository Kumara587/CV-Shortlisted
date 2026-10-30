"""Single-origin Render entrypoint; private secrets are materialized only at runtime."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from encryption import private_write


def prepare_environment():
    hostname=os.environ.get('RENDER_EXTERNAL_HOSTNAME','')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]+\.onrender\.com',hostname):
        raise ValueError('Render hostname is missing or invalid.')
    os.environ.setdefault('ALLOWED_HOSTS',hostname)
    os.environ.setdefault('CORS_ORIGINS','https://'+hostname)
    os.environ.setdefault('APP_ENV','production')
    os.environ.setdefault('PARSER_CONCURRENCY','1')
    os.environ.setdefault('AUTH_CONCURRENCY','1')
    os.environ.setdefault('CLEANUP_INTERVAL_SECONDS','0')
    os.environ.setdefault('SCREENER_SCHEMA_MODE','verify-only')
    os.environ.setdefault('XDG_CONFIG_HOME','/tmp/cv-caddy/config')
    os.environ.setdefault('XDG_DATA_HOME','/tmp/cv-caddy/data')
    root=Path(tempfile.mkdtemp(prefix='cv-runtime-'))
    os.environ['SCREENER_DATA_DIR']=str(root/'data')
    for source,target,filename in [
        ('SCREENER_STORAGE_KEY_JSON','SCREENER_KEY_FILE','storage.keys.json'),
        ('SCREENER_GEMINI_JSON','GEMINI_CONFIG_FILE','gemini.credentials.json'),
        ('SCREENER_AUTH_JSON','AUTH_CONFIG_FILE','auth.credentials.json')]:
        value=os.environ.pop(source,None)
        if value is None:
            if source=='SCREENER_AUTH_JSON':value='{}'
            else:raise ValueError('A required runtime secret is missing.')
        parsed=json.loads(value)
        if not isinstance(parsed,dict):raise ValueError('A runtime secret is invalid.')
        if source=='SCREENER_AUTH_JSON':parsed['app_url']='https://'+hostname
        path=root/filename
        private_write(path,json.dumps(parsed).encode())
        os.environ[target]=str(path)
    if not os.environ.get('DATABASE_URL','').startswith('postgresql://'):
        raise ValueError('Neon database connection is missing.')
    return root


def main():
    try:prepare_environment()
    except Exception:
        print('Startup configuration failed. Check runtime secret names and the Render hostname.',flush=True)
        raise SystemExit(1)
    processes=[]
    stopping=False
    def stop(*args):
        nonlocal stopping
        stopping=True
        for process in processes:
            if process.poll() is None:process.terminate()
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:
        processes.append(subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port','8000','--workers','1','--proxy-headers','--forwarded-allow-ips','127.0.0.1','--no-access-log','--log-config','/app/logging.json']))
        processes.append(subprocess.Popen(['caddy','run','--config','/app/Caddyfile','--adapter','caddyfile']))
        while not stopping and all(p.poll() is None for p in processes):time.sleep(0.5)
        exit_code=0 if stopping else 1
    finally:
        stop()
        for process in processes:
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill()
    raise SystemExit(exit_code)


if __name__=='__main__':main()

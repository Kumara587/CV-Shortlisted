"""Create an isolated local cluster from already-installed PostgreSQL binaries."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
from urllib.parse import quote
import psycopg
from psycopg import sql
from encryption import private_write,StorageSecurityError
from local_postgres import config_path,control


def setup(bin_dir,data_dir,port):
    bin_dir=Path(bin_dir).resolve();data_dir=Path(data_dir).resolve()
    if not (bin_dir/'initdb.exe').is_file():raise StorageSecurityError('Usable PostgreSQL binaries were not found.')
    path=config_path()
    if path.exists():
        config=json.loads(path.read_text())
        if Path(config['bin'])!=bin_dir or Path(config['data'])!=data_dir or config['port']!=port:
            raise StorageSecurityError('A different local runtime configuration exists; it was not overwritten.')
    else:
        config={'bin':str(bin_dir),'data':str(data_dir),'port':port,'admin_user':'cv_admin',
                'admin_password':secrets.token_urlsafe(32),'app_user':'cv_app','app_password':secrets.token_urlsafe(32)}
        private_write(path,json.dumps(config).encode())
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    if not (data_dir/'PG_VERSION').exists():
        if data_dir.exists() and any(data_dir.iterdir()):raise StorageSecurityError('Cluster directory is not empty; existing files were not changed.')
        data_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        if os.name=='nt':
            identity=subprocess.check_output(['whoami'],text=True).strip()
            subprocess.run(['icacls',str(data_dir),'/inheritance:r','/grant:r',identity+':(OI)(CI)(F)'],check=True,capture_output=True)
        password_file=path.parent/'postgres-init.password'
        private_write(password_file,config['admin_password'].encode())
        try:
            result=subprocess.run([str(bin_dir/'initdb.exe'),'-D',str(data_dir),'-U',config['admin_user'],
                '--encoding=UTF8','--locale=C','--auth-host=scram-sha-256','--auth-local=scram-sha-256',
                '--pwfile='+str(password_file)],capture_output=True,creationflags=flags)
            if result.returncode:raise StorageSecurityError('PostgreSQL cluster initialization failed. Existing files were not deleted.')
        finally:password_file.unlink(missing_ok=True)
        with (data_dir/'postgresql.conf').open('a') as stream:
            stream.write("\nlisten_addresses = '127.0.0.1'\nport = "+str(port)+"\npassword_encryption = 'scram-sha-256'\nmax_connections = 30\nshared_buffers = '64MB'\nlog_statement = 'none'\nlog_min_error_statement = 'panic'\nlog_parameter_max_length_on_error = 0\n")
    control('start')
    with psycopg.connect(host='127.0.0.1',port=port,user=config['admin_user'],password=config['admin_password'],dbname='postgres',autocommit=True,connect_timeout=5) as db:
        if not db.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(config['app_user'],)).fetchone():
            db.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE').format(sql.Identifier(config['app_user']),sql.Literal(config['app_password'])))
        for name in ['cv_shortlisted','cv_shortlisted_test']:
            if not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():
                db.execute(sql.SQL('CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING {}').format(sql.Identifier(name),sql.Identifier(config['app_user']),sql.Literal('UTF8')))
    for name,filename in [('cv_shortlisted','postgres.target.url'),('cv_shortlisted_test','postgres.test.url')]:
        url=f"postgresql://{config['app_user']}:{quote(config['app_password'],safe='')}@127.0.0.1:{port}/{name}?sslmode=disable"
        destination=path.parent/filename
        if destination.exists():
            if destination.read_text()!=url:raise StorageSecurityError('Existing private connection file differs; it was not replaced.')
        else:private_write(destination,url.encode())
    print('Isolated local PostgreSQL ready on 127.0.0.1:'+str(port))
    print('Application database: cv_shortlisted; role: cv_app (not a server superuser).')
    print('Private connection files created. Credentials were not printed.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--bin-dir',required=True);parser.add_argument('--data-dir',required=True)
    parser.add_argument('--port',type=int,default=5433)
    args=parser.parse_args()
    try:setup(args.bin_dir,args.data_dir,args.port)
    except (StorageSecurityError,OSError,psycopg.Error,ValueError,subprocess.SubprocessError):
        parser.exit(1,'Local PostgreSQL setup stopped. Check binaries, free disk space, port and the private runtime configuration; credentials were not printed.\n')

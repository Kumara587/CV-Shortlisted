"""Manage the isolated user-owned local cluster; credentials are never printed."""
import json
import os
from pathlib import Path
import subprocess
from encryption import StorageSecurityError


def config_path():
    root=Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.config')))
    return root/'CVShortlisted'/'secrets'/'local-postgres.json'


def control(action):
    try:
        config=json.loads(config_path().read_text())
        executable=Path(config['bin'])/'pg_ctl.exe'
        data=Path(config['data'])
        if not executable.is_file() or not data.is_dir():raise ValueError()
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        status=subprocess.run([str(executable),'-D',str(data),'status'],capture_output=True,creationflags=flags)
        if action=='start' and status.returncode==0:return 'Local PostgreSQL is already running.'
        if action=='stop' and status.returncode!=0:return 'Local PostgreSQL is already stopped.'
        if action=='start':
            args=[str(executable),'-D',str(data),'-l',str(data.parent/'postgres.log'),'-o',f"-h 127.0.0.1 -p {int(config['port'])}",'-w','start']
        else:args=[str(executable),'-D',str(data),'-m','fast','-w','stop']
        # A long-lived Windows server may inherit pipe handles: don't wait on
        # captured stdout/stderr after pg_ctl has already finished starting it.
        result=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,timeout=60,creationflags=flags)
        if result.returncode:raise ValueError()
        return 'Local PostgreSQL '+('started.' if action=='start' else 'stopped.')
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):
        raise StorageSecurityError('Local PostgreSQL control failed. Check the private runtime configuration and PostgreSQL log.') from None

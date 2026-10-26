"""Local administrator tool. Tokens are shown once; never save them in frontend files."""
import argparse
import os
import sqlite3
from pathlib import Path
from security import Settings
from store import Store

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['create-user','revoke-user','purge'])
    parser.add_argument('name',nargs='?')
    args=parser.parse_args()
    settings=Settings.environment()
    store=Store(Path(os.getenv('SCREENER_DATA_DIR',str(Path(__file__).parent/'data')))/'screener.sqlite3',settings.ttl)
    if args.action=='purge':
        print('Expired snapshots deleted:',store.purge())
    elif not args.name or len(args.name)>80 or not args.name.replace('-','').replace('_','').isalnum():
        parser.error('Use an account name of 1–80 letters/digits/underscore/hyphen')
    elif args.action=='create-user':
        try: _,token=store.create_user(args.name)
        except sqlite3.IntegrityError:
            parser.exit(1,'Account name already exists. Use its existing access token, or create an account with a different name. Tokens cannot be recovered.\n')
        except Exception:
            parser.exit(1,'Could not create account. Choose a unique account name and check data-directory access.\n')
        print('Copy this access token into the app. It is shown only once:\n'+token)
    else:
        print('Account revoked and snapshots deleted.' if store.revoke(args.name) else 'Account not found.')

if __name__=='__main__': main()

"""Local administrator tool. Tokens are shown once; never save them in frontend files."""
import argparse
import os
import sqlite3
from getpass import getpass
from pathlib import Path
from security import Settings
from store import Store
from encryption import initialize_key, key_path, Cipher, StorageSecurityError, backup_key, restore_key
from storage_admin import migrate, backup, restore

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['create-user','revoke-user','purge','init-encryption','migrate-encryption','verify-encryption','backup-data','restore-data','backup-key','restore-key'])
    parser.add_argument('name',nargs='?')
    parser.add_argument('--output',help='New encrypted backup or restored database path; never overwritten')
    parser.add_argument('--backup',help='Encrypted backup source for restore-data')
    args=parser.parse_args()
    settings=Settings.environment()
    store=Store(Path(os.getenv('SCREENER_DATA_DIR',str(Path(__file__).parent/'data')))/'screener.sqlite3',settings.ttl)
    if args.action=='init-encryption':
        try:
            path=initialize_key()
            print('Encryption key created outside the database. Keep a separate protected backup of:',path)
        except FileExistsError: parser.exit(1,'Key file already exists; it was not replaced.\n')
        except (StorageSecurityError,OSError): parser.exit(1,'Could not create the private key file. Check its directory and permissions.\n')
    elif args.action in {'migrate-encryption','verify-encryption','backup-data','restore-data','backup-key','restore-key'}:
        try:
            if args.action=='migrate-encryption':
                if not args.output: parser.error('migrate-encryption requires --output for its encrypted recovery backup')
                print('Encrypted records verified:',migrate(store,args.output))
            elif args.action=='verify-encryption':
                from encryption import verify_fields
                with store.connection() as db: print('Encrypted records verified:',verify_fields(db,store.cipher))
            elif args.action=='backup-data':
                if not args.output: parser.error('backup-data requires --output')
                backup(store,args.output); print('Encrypted backup created and verified.')
            elif args.action=='backup-key':
                if not args.output: parser.error('backup-key requires --output on separate protected storage')
                password=getpass('Recovery passphrase (at least 16 characters): ')
                if password!=getpass('Confirm recovery passphrase: '):
                    raise StorageSecurityError('Passphrases do not match.')
                backup_key(args.output,password)
                print('Password-encrypted key backup created. Store its passphrase separately.')
            elif args.action=='restore-key':
                if not args.backup: parser.error('restore-key requires --backup')
                restore_key(args.backup,args.output or key_path(),getpass('Recovery passphrase: '))
                print('Key restored to a new private file. Existing keys were not overwritten.')
            else:
                if not args.backup or not args.output: parser.error('restore-data requires --backup and --output')
                restore(args.backup,args.output,Cipher.load()); print('Recovery database created and encrypted; existing database unchanged.')
        except (StorageSecurityError,OSError,sqlite3.Error) as exc:
            message=str(exc) if isinstance(exc,StorageSecurityError) else 'Storage operation failed. Check paths, available space, permissions and database locks.'
            parser.exit(1,message+'\n')
    elif args.action=='purge':
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

"""Attach email/password login to an existing administrator-created account."""
import argparse
from getpass import getpass
from auth import EmailInput,password_hash,validate_password
from store import open_store

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--legacy-name',required=True,help='Existing admin-created account name; keeps its data owner ID')
    args=parser.parse_args()
    store=open_store()
    with store.connection() as db:
        row=db.execute('SELECT id FROM users WHERE name=? AND active=1',(args.legacy_name,)).fetchone()
        if not row:parser.exit(1,'Existing active account not found. No changes made.\n')
        owner=row['id']
        if db.execute('SELECT id FROM auth_accounts WHERE id=?',(owner,)).fetchone():parser.exit(1,'Account already has email login. Use password recovery; nothing overwritten.\n')
    email=EmailInput(email=input('Email address: ')).email
    password=getpass('New password (8+ characters with uppercase, lowercase, number and special character; hidden): ')
    try:validate_password(password)
    except ValueError:parser.exit(1,'Password does not meet the requirements. Nothing saved.\n')
    if password!=getpass('Confirm password (hidden): '):parser.exit(1,'Passwords must match. Nothing saved.\n')
    # Local admin attests the address belongs to this account owner.
    store.register_account(email,args.legacy_name,password_hash(password),verified=True,owner=owner)
    print('Email login attached to the existing owner. Saved jobs/history remain attached. No password printed.')

if __name__=='__main__':main()

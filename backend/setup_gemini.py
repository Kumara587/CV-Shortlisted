"""Run interactively; the API key is never printed or placed in command arguments."""
import json
from getpass import getpass
from encryption import private_write
from gemini_provider import config_path,valid_key


def main():
    path=config_path()
    if path.exists():
        print('Gemini configuration already exists; it was not overwritten.')
        return
    print('Gemini demo: use only fake/sample CVs. Free-tier content may be used by Google for product improvement.')
    key=getpass('Paste Gemini API key (hidden): ').strip()
    if not valid_key(key):
        raise SystemExit('Key must be a single value without spaces, surrounding quotes or line breaks. Nothing saved.')
    private_write(path,json.dumps({'provider':'gemini','model':'gemini-3.1-flash-lite','synthetic_only':True,'api_key':key}).encode())
    print('Private Gemini configuration saved. No key was printed. The running backend reads it on the next request.')


if __name__=='__main__':main()

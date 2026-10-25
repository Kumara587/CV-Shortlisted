"""Disposable local parser; input bytes are never saved."""
import json
import sys
from parsing import MAX_BYTES, parse_file

if __name__ == '__main__':
    if sys.platform != 'win32':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (768*1024*1024,768*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU, (10,10))
        resource.setrlimit(resource.RLIMIT_CORE, (0,0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0,0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64,64))
    data = sys.stdin.buffer.read(MAX_BYTES + 1)
    result = parse_file(data, sys.argv[1], sys.argv[2])
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=True).encode('utf-8'))

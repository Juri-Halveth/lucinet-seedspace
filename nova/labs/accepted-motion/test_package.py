"""Exercise the documented standard-library server and exact asset routes."""
import functools
import hashlib
import json
from pathlib import Path
import socketserver
import threading
import urllib.request
from serve import MotionHandler

root = Path(__file__).resolve().parent
class QuietHandler(MotionHandler):
    def log_message(self, *args):
        pass

handler = functools.partial(QuietHandler, directory=str(root))
manifest = json.loads((root/'FROZEN_FILES.json').read_bytes())
with socketserver.TCPServer(('127.0.0.1', 0), handler) as server:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = 'http://127.0.0.1:' + str(server.server_address[1])
        for entry in manifest['files']:
            with urllib.request.urlopen(base+'/'+entry['path'], timeout=5) as response:
                body = response.read()
                assert hashlib.sha256(body).hexdigest() == entry['sha256'], entry['path']
                if entry['path'].endswith(('.mjs', '.js')):
                    assert 'javascript' in response.headers['Content-Type'], entry['path']
        for route, marker in [('/motion/', b'world'), ('/universum', b'/motion/')]:
            with urllib.request.urlopen(base+route, timeout=5) as response:
                assert marker in response.read(), route
    finally:
        server.shutdown()
        thread.join(timeout=5)
print(json.dumps({'asset_routes': len(manifest['files']), 'entry_and_return_routes': 2, 'passed': True}))

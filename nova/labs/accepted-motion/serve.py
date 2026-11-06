"""Loopback-only static server with deterministic JavaScript module MIME types."""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class MotionHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'text/javascript', '.mjs': 'text/javascript',
                      '.css': 'text/css', '.glb': 'model/gltf-binary'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=31350)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be in 1..65535')
    handler = functools.partial(MotionHandler, directory=str(Path(__file__).resolve().parent))
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        print(f'http://127.0.0.1:{args.port}/motion/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

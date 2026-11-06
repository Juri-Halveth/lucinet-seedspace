"""Verify the exact accepted files; read-only, no model or network access."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'FROZEN_FILES.json').read_bytes())
errors = []
seen = set()
for record in manifest['files']:
    path = (root / record['path']).resolve()
    if not path.is_relative_to(root) or record['path'] in seen:
        raise SystemExit('Invalid manifest path')
    seen.add(record['path'])
    data = path.read_bytes()
    if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
        errors.append(record['path'])
result = {'files': len(seen), 'mismatches': errors,
          'claim': 'Byte identity of the preserved files; visual acceptance is recorded separately'}
print(json.dumps(result))
raise SystemExit(1 if errors else 0)

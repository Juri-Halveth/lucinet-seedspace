import hashlib
import json
from pathlib import Path
import tempfile
from measure import measure

root = Path(__file__).resolve().parent
manifest = json.loads((root/'FROZEN_FILES.json').read_bytes())
with tempfile.TemporaryDirectory(prefix='nova-motion-wrapper-test-') as temp:
    destination = Path(temp)/'new-results'
    result = measure(destination)
    assert result['variants'] == 2
    for name, supported in [('motion-baseline.json', False), ('motion-candidate.json', True)]:
        receipt = json.loads((destination/name).read_bytes())
        assert receipt['frames'] == 660
        assert receipt['contract']['supportLock'] is supported
        assert len(receipt['trace']) == 660
    try:
        measure(destination)
    except FileExistsError:
        pass
    else:
        raise AssertionError('Existing evidence must not be overwritten')
for record in manifest['files']:
    assert hashlib.sha256((root/record['path']).read_bytes()).hexdigest() == record['sha256']
print(json.dumps({'both_variants': True, 'frames_each': 660, 'existing_output_preserved': True,
                  'frozen_files_unchanged': len(manifest['files'])}))

"""Run the frozen measurement script in an isolated layout, preserving its bytes."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

def measure(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Choose a new output directory; existing measurements are preserved')
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='nova-accepted-motion-') as temp:
        temp_root = Path(temp).resolve()
        runtime = temp_root/'export/lab/motion'
        assert runtime.is_relative_to(temp_root)
        shutil.copytree(root/'motion', runtime)
        output = temp_root/'results'
        output.mkdir()
        # The original script binds ../../../results to its own module location.
        subprocess.run(['node', str(runtime/'measure-motion.mjs')], check=True, timeout=120,
                       stdout=subprocess.DEVNULL)
        parsed = {name: json.loads((output/name).read_bytes()) for name in
                  ('motion-baseline.json', 'motion-candidate.json')}
        if any(record['frames'] != 660 for record in parsed.values()):
            raise ValueError('Incomplete measurement')
        destination.mkdir(parents=True, exist_ok=False)
        for name in parsed:
            shutil.copyfile(output/name, destination/name)
    return {'output': str(destination), 'variants': len(parsed), 'frames_each': 660,
            'frozen_source_unchanged': True}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', help='New directory for both measurement receipts')
    args = parser.parse_args()
    print(json.dumps(measure(args.output)))

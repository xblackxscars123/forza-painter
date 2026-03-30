#!/usr/bin/env python3
"""
Run a small sample through the image pipeline (first 5 images under imgs/).
"""
import glob
import subprocess
import sys
from pathlib import Path

files = [f for f in glob.glob('imgs/**/*', recursive=True) if f.lower().endswith(('.png','.jpg','.jpeg','.webp','.bmp','.gif'))][:5]
if not files:
    print('No images found under imgs/')
    raise SystemExit(1)

print('Files to process:')
for f in files:
    print(' -', f)

cmd = [sys.executable, 'image_pipeline.py'] + files + ['-o', 'output_sample', '--scale', '2', '--skip-low-quality', '--optimize-passes', '1', '--no-remove-bg', '--suffix', '_raw']
print('\nRunning:')
print(' '.join(cmd))

proc = subprocess.run(cmd)
print('\nExit code:', proc.returncode)

if proc.returncode != 0:
    raise SystemExit(proc.returncode)

print('\nDone.')

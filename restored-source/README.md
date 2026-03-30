# Restored Legacy Source (Historical)

This folder contains recovered historical Python source from the public `forza-painter` repository history.

## Provenance
- Repository: https://github.com/forza-painter/forza-painter
- Last Python revision before removal: `dead4f3bc753005a1a7e0e73332d1506a170fd5f`
- Python file deletion commit: `4c6cbf6`

## Purpose
- Reference for research and reverse engineering.
- Baseline for understanding old memory offsets, geometry import flow, and shape mapping.

## Notes
- This source targets older game builds and older tooling assumptions.
- It is not guaranteed to work with current Forza versions.
- Running requires Administrator privileges and Windows-specific APIs.

## Quick setup
1. Create a Python 64-bit virtual environment.
2. Install dependencies from requirements.txt.
3. Run python legacy-python/main.py <generated_geometry.json>.

## Modernized dev runner
1. Open restored-source/dev-python.
2. Install dependencies from dev-python/requirements.txt.
3. Run preview mode:
   python dev_runner.py --input C:\path\to\generated_geometry.json --preview
4. Run injection mode (Administrator):
   python dev_runner.py --input C:\path\to\generated_geometry.json --inject

## Files
- legacy-python/main.py
- legacy-python/native.py
- legacy-python/internal_classes.py
- dev-python/dev_runner.py

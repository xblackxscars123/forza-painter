# Dev Python Runner

This is a modernized development runner built from the recovered legacy logic.

## Features
- Safe preview-only mode for local geometry validation.
- Optional live injection mode for Forza memory writes.
- Better CLI flow and clearer errors.

## Usage
- Preview only:
  - python dev_runner.py --input C:\path\to\image.json --preview
- Preview and save image:
  - python dev_runner.py --input C:\path\to\image.json --preview --preview-path preview.png
- Attempt injection:
  - python dev_runner.py --input C:\path\to\image.json --inject

## Car Color Paster
Use this helper when you want to paste HEX or HSB color values into the active car color fields.

- Convert from HEX and copy HSB triplet to clipboard:
  - python color_paster.py --hex #FF8800
- Convert from HSB and copy RGB triplet to clipboard:
  - python color_paster.py --hsb 210,70,85 --target rgb
- Auto-paste triplet into active fields (focus the first color field first):
  - python color_paster.py --hex #4AA3FF --apply --delay 2.5 --confirm
- Auto-paste with explicit foreground window matching:
  - python color_paster.py --hsb 210,70,85 --apply --window-substring Forza --window-timeout 30

Notes:
- The script copies a comma-separated triplet to clipboard in all modes.
- With --apply, it pastes each channel value and tabs to the next field.
- With --apply, it first waits for a foreground Forza process window whose title contains the configured text.
- pywin32 is required for clipboard and keyboard automation.

## Notes
- Injection mode requires Windows and Administrator privileges.
- Injection offsets may drift across game versions.
- Preview mode does not require Forza to be running.

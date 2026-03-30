@echo off
REM Drag and drop image files onto this .bat to convert them to PNG using convert_to_png.py

REM Change directory to the script location
cd /d %~dp0

REM Loop through all dropped files
for %%F in (%*) do (
    python convert_to_png.py "%%F"
)

pause
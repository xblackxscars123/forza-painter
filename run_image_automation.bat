@echo off
setlocal
cd /d "%~dp0"

if not exist "image_pipeline.py" (
  echo [ERROR] image_pipeline.py not found.
  echo Place this .bat in the forza-painter folder.
  pause
  exit /b 1
)

if "%~1"=="" (
  echo Running image pipeline on all files under .\imgs ...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$imgs = Get-ChildItem '.\imgs' -Recurse -File | Where-Object { $_.Extension -match '\.(png|jpg|jpeg|webp|bmp|gif)$' }; if (-not $imgs) { Write-Host '[ERROR] No images found in .\imgs'; exit 1 }; python .\image_pipeline.py $imgs.FullName -o .\output --scale 2 --skip-low-quality --optimize-passes 3 --no-remove-bg --suffix _raw"
  set "RC=%ERRORLEVEL%"
) else (
  echo Running image pipeline on dropped/provided files...
  python .\image_pipeline.py %* -o .\output --scale 2 --skip-low-quality --optimize-passes 3 --no-remove-bg --suffix _raw
  set "RC=%ERRORLEVEL%"
)

if not "%RC%"=="0" (
  echo.
  echo Pipeline finished with errors. Exit code: %RC%
) else (
  echo.
  echo Pipeline complete. Results are in .\output
)

pause
exit /b %RC%

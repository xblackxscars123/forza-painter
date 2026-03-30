@echo off
:: Build image_pipeline.exe with PyInstaller
:: Run this once to produce dist\image_pipeline.exe
::
:: Prerequisites:
::   pip install pyinstaller
::   pip install -r requirements.txt

echo --- Installing / verifying dependencies ---
pip install -r requirements.txt
pip install pyinstaller

echo.
echo --- Building exe ---

pyinstaller ^
    --onefile ^
    --name "image_pipeline" ^
    --hidden-import onnxruntime ^
    --hidden-import onnxruntime.capi._pybind_state ^
    --hidden-import rembg ^
    --hidden-import rembg.sessions ^
    --hidden-import rembg.sessions.u2net ^
    --collect-all rembg ^
    --collect-all onnxruntime ^
    --hidden-import cv2 ^
    --collect-all cv2 ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --hidden-import tkinter.scrolledtext ^
    --hidden-import oxipng ^
    --icon NONE ^
    image_pipeline.py

echo.
echo ============================================================
echo  Build complete:  dist\image_pipeline.exe
echo.
echo  FIRST RUN NOTE:
echo  rembg will download the U2Net model (~176 MB) to:
echo      %%USERPROFILE%%\.u2net\u2net.onnx
echo  This only happens once.
echo ============================================================

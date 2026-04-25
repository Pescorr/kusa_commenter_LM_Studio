@echo off
chcp 65001 >nul
echo ============================================================
echo   kusa_commenter_LM_Studio - Build Script (v1.1.0+)
echo ============================================================
echo.

echo [1/5] Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller
echo.

echo [2/5] Building with PyInstaller (5-10 min for llama_server copy)...
pyinstaller screen_commentator.spec --clean --noconfirm
echo.

if errorlevel 1 (
    echo ============================================================
    echo   Build FAILED! Check the error messages above.
    echo ============================================================
    pause
    exit /b 1
)

set "DIST=dist\ScreenCommentator"

echo [3/5] Moving llama_server to root next to exe...
if exist "%DIST%\_internal\llama_server" (
    move /Y "%DIST%\_internal\llama_server" "%DIST%\llama_server" >nul
)
echo.

echo [4/5] Copying config.ini and setup_model.bat to root...
copy /Y config.ini "%DIST%\config.ini" >nul
copy /Y setup_model.bat "%DIST%\setup_model.bat" >nul
echo.

echo [5/5] Removing duplicate DLLs from _internal/ (PyInstaller binary reclassification)...
del /F /Q "%DIST%\_internal\cublas64_12.dll" 2>nul
del /F /Q "%DIST%\_internal\cublasLt64_12.dll" 2>nul
del /F /Q "%DIST%\_internal\cudart64_12.dll" 2>nul
del /F /Q "%DIST%\_internal\ggml-base.dll" 2>nul
del /F /Q "%DIST%\_internal\ggml.dll" 2>nul
del /F /Q "%DIST%\_internal\llama-common.dll" 2>nul
del /F /Q "%DIST%\_internal\llama.dll" 2>nul
del /F /Q "%DIST%\_internal\config.ini" 2>nul
del /F /Q "%DIST%\_internal\setup_model.bat" 2>nul
echo.

echo ============================================================
echo   Build complete!
echo   Output: %DIST%\
echo   Run:    %DIST%\ScreenCommentator.exe
echo   First-run setup: %DIST%\setup_model.bat
echo ============================================================
echo.
pause

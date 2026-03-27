@echo off
chcp 65001 >nul
echo ============================================================
echo   Screen Commentator - Build Script
echo ============================================================
echo.

echo [1/4] Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller
echo.

echo [2/4] Building with PyInstaller...
pyinstaller screen_commentator.spec --clean --noconfirm
echo.

if errorlevel 1 (
    echo ============================================================
    echo   Build FAILED! Check the error messages above.
    echo ============================================================
    pause
    exit /b 1
)

echo [3/4] Copying config.ini to output folder...
copy /Y config.ini dist\ScreenCommentator\config.ini >nul
echo.

echo [4/4] Build complete!
echo.
echo ============================================================
echo   Output: dist\ScreenCommentator\
echo   Run:    dist\ScreenCommentator\ScreenCommentator.exe
echo ============================================================
echo.
pause

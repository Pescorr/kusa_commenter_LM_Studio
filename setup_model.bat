@echo off
chcp 65001 >NUL
setlocal

echo ============================================================
echo   kusa_commenter Vision model downloader
echo ============================================================
echo.
echo   Source: unsloth/Qwen3.5-9B-GGUF (HuggingFace)
echo   Total:  about 6.2 GB
echo     - Qwen3.5-9B-Q4_K_M.gguf (5.3 GB)
echo     - mmproj-BF16.gguf       (879 MB)
echo.
echo   Saved to:    %~dp0models
echo   Resumable:   re-run this script to continue an interrupted DL
echo ============================================================
echo.

set "MODEL_DIR=%~dp0models"
if not exist "%MODEL_DIR%" mkdir "%MODEL_DIR%"

set "BASE_URL=https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main"

echo [1/2] Downloading Qwen3.5-9B-Q4_K_M.gguf ...
curl.exe -L -C - --retry 5 --retry-delay 10 -o "%MODEL_DIR%\Qwen3.5-9B-Q4_K_M.gguf" "%BASE_URL%/Qwen3.5-9B-Q4_K_M.gguf?download=true"
if errorlevel 1 (
  echo.
  echo ERROR: Failed to download the LLM model.
  pause
  exit /b 1
)
echo.

echo [2/2] Downloading mmproj-BF16.gguf ...
curl.exe -L -C - --retry 5 --retry-delay 10 -o "%MODEL_DIR%\mmproj-BF16.gguf" "%BASE_URL%/mmproj-BF16.gguf?download=true"
if errorlevel 1 (
  echo.
  echo ERROR: Failed to download the mmproj.
  pause
  exit /b 1
)
echo.

echo ============================================================
echo   Done. Now run ScreenCommentator.exe
echo ============================================================
echo.
pause
endlocal

@echo off
chcp 65001 >nul
setlocal

echo ============================================================
echo   kusa_commenter Vision モデルダウンロード
echo ============================================================
echo.
echo   モデル: unsloth/Qwen3.5-9B-GGUF
echo   合計サイズ: 約 6.2 GB
echo   - Qwen3.5-9B-Q4_K_M.gguf (5.3 GB)
echo   - mmproj-BF16.gguf       (879 MB)
echo.
echo   ダウンロード先: %~dp0models\
echo   ※ 中断しても -C - で再開できます
echo ============================================================
echo.

set "MODEL_DIR=%~dp0models"
if not exist "%MODEL_DIR%" mkdir "%MODEL_DIR%"

set "BASE_URL=https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main"

echo [1/2] Qwen3.5-9B-Q4_K_M.gguf をダウンロード中...
curl.exe -L -C - --retry 5 --retry-delay 10 ^
  -o "%MODEL_DIR%\Qwen3.5-9B-Q4_K_M.gguf" ^
  "%BASE_URL%/Qwen3.5-9B-Q4_K_M.gguf?download=true"
if errorlevel 1 (
  echo.
  echo ERROR: モデル本体のダウンロードに失敗しました
  pause
  exit /b 1
)
echo.

echo [2/2] mmproj-BF16.gguf をダウンロード中...
curl.exe -L -C - --retry 5 --retry-delay 10 ^
  -o "%MODEL_DIR%\mmproj-BF16.gguf" ^
  "%BASE_URL%/mmproj-BF16.gguf?download=true"
if errorlevel 1 (
  echo.
  echo ERROR: mmproj のダウンロードに失敗しました
  pause
  exit /b 1
)
echo.

echo ============================================================
echo   ダウンロード完了
echo ============================================================
echo.
echo   このウィンドウを閉じて ScreenCommentator.exe を実行してください
echo.
pause
endlocal

# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Screen Commentator (v1.1.0 - llama.cpp 同梱版)

import os
import glob

block_cipher = None

# === llama-server バイナリの収集 ===
LLAMA_SRC = r'R:/AI/LLM_Servers/llama_server'
# CUDA 13 系は容量削減のため除外（CUDA 12 で十分）
EXCLUDE_FILES = {
    'cublasLt64_13.dll',
    'cublas64_13.dll',
    'cudart64_13.dll',
}
# 同梱しないサブフォルダ
EXCLUDE_DIRS = {'_update_backup', 'configs'}

llama_files = []
if os.path.isdir(LLAMA_SRC):
    for entry in os.listdir(LLAMA_SRC):
        full = os.path.join(LLAMA_SRC, entry)
        if not os.path.isfile(full):
            continue
        if entry in EXCLUDE_FILES:
            continue
        # exe / dll のみ同梱（その他は configs/ で個別管理）
        if entry.endswith('.exe') or entry.endswith('.dll'):
            llama_files.append((full, 'llama_server'))


a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('config.ini', '.'),
        ('setup_model.bat', '.'),
        # llama-server バイナリ群を datas として配置（dependency 解析を避ける）
    ] + llama_files,
    hiddenimports=[
        'pystray',
        'pystray._win32',
        'pynput',
        'pynput.keyboard',
        'pynput.keyboard._win32',
        'pynput.mouse',
        'pynput.mouse._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'mss',
        'mss.windows',
        'monitor_utils',
        'llama_server_manager',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ScreenCommentator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    # llama-server の DLL を UPX で圧縮しない（破損リスク回避）
    upx_exclude=['ggml-cuda.dll', 'cublasLt64_12.dll', 'cublas64_12.dll', 'llama-server.exe'],
    name='ScreenCommentator',
)

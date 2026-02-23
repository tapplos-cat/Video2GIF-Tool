# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['video_to_gif.py'], # 确认这里是你代码的文件名
    pathex=[],
    binaries=[],
    datas=[], 
    hiddenimports=['PIL', 'numpy'],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Video2GIF_Tool', # 这是你exe最终的文件名
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True, # 设为 True 可以在下载ffmpeg时看到黑窗口进度
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

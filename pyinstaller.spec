# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# 定义项目中的资源文件（模型文件、配置文件等）
# 格式为：(文件名, 目标文件夹名)
added_files = [
    ('detect.caffemodel', '.'),
    ('detect.prototxt', '.'),
    ('sr.caffemodel', '.'),
    ('sr.prototxt', '.'),
    # 如果你有默认配置文件也可以加入
    # ('camera_default_config.json', '.'),
]

# 自动收集一些库的必要数据文件
datas = added_files
datas += collect_data_files('pyzbar')

# 检查是否存在本地的 IMVApi 文件夹，如果想把 SDK 包装进程序，可以在这里设置
# 但根据你的代码，它是从 C:/Program Files/HuarayTech/... 读取的，建议保持外部安装

a = Analysis(
    ['camera_app.py'],  # 主程序入口
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'cv2',
        'numpy',
        'pyzbar'
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
    name='CameraCodeReadApp', # 生成的 exe 名称
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # 设置为 False 则运行程序时不会弹出黑色命令行窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements=None,
    icon=['icon.ico'], 
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CameraCodeReadApp', # 生成的安装文件夹名称
)
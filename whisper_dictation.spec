# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Whisper Dictation (Windows)
#
# Build:
#   pyinstaller whisper_dictation.spec
#
# Output: dist/WhisperDictation/WhisperDictation.exe
#
# Notes:
#   - The Whisper model is NOT bundled. It is downloaded (~460 MB) on first run
#     and cached in %USERPROFILE%\.cache\huggingface\hub\.
#   - CUDA DLLs (nvidia-* pip packages) are NOT bundled — they add 1.2 GB.
#     GPU acceleration works automatically if the target PC has CUDA Toolkit
#     12.x installed system-wide. Without it the app falls back to CPU.

from PyInstaller.utils.hooks import collect_all, collect_data_files

# Collect all files (code + data + binaries) for these packages
faster_whisper_datas,    faster_whisper_bins,    faster_whisper_hiddens    = collect_all('faster_whisper')
ctranslate2_datas,       ctranslate2_bins,       ctranslate2_hiddens       = collect_all('ctranslate2')
tokenizers_datas,        tokenizers_bins,        tokenizers_hiddens        = collect_all('tokenizers')
huggingface_hub_datas,   huggingface_hub_bins,   huggingface_hub_hiddens   = collect_all('huggingface_hub')
av_datas,                av_bins,                av_hiddens                = collect_all('av')

all_datas = (
    faster_whisper_datas +
    ctranslate2_datas +
    tokenizers_datas +
    huggingface_hub_datas +
    av_datas +
    collect_data_files('soundfile')
)

all_binaries = (
    faster_whisper_bins +
    ctranslate2_bins +
    tokenizers_bins +
    huggingface_hub_bins +
    av_bins
)

all_hiddens = (
    faster_whisper_hiddens +
    ctranslate2_hiddens +
    tokenizers_hiddens +
    huggingface_hub_hiddens +
    av_hiddens + [
        'sounddevice',
        'soundfile',
        'scipy',
        'scipy.signal',
        'pyperclip',
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'psutil',
        'winsound',
        'numpy',
    ]
)

a = Analysis(
    ['whisper_dictate.py'],
    pathex=[],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddens,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude CUDA pip packages — too large (1.2 GB) for bundling.
    # GPU works if CUDA Toolkit is installed system-wide on the target PC.
    excludes=[
        'nvidia',
        'torch', 'torchvision', 'torchaudio',
        'tensorflow', 'keras',
        'matplotlib', 'pandas', 'sklearn',
        'IPython', 'jupyter',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WhisperDictation',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # no console window (equivalent to pythonw)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,          # add a .ico file path here if you want a custom icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WhisperDictation',
)

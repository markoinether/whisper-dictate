# Whisper Dictation

A lightweight background app that transcribes speech and pastes the result directly into any active window. Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for fully offline transcription.

## Features

- One hotkey to start and stop recording (`Ctrl+Alt+R` by default)
- Transcribed text is pasted immediately into whatever window you are typing in
- Auto-detects language, constrained to English and Slovak (configurable)
- System tray icon: grey = ready, red = recording
- Audio beeps on start and stop
- GPU-accelerated on NVIDIA hardware; falls back to CPU automatically
- Fully offline after first run — no API key, no internet
- Single-instance enforced: launching again kills the previous instance

## Platform support

| Platform | Status |
|----------|--------|
| Windows 10 / 11 | Supported |
| Linux | Planned |
| macOS | Planned |

---

## Windows installation

### Prerequisites

- Python 3.10 or later — [python.org](https://www.python.org/downloads/)
- An NVIDIA GPU is optional but recommended for speed

### One-step install

```bat
launchers\windows\install.bat
```

This installs all Python packages, optionally installs CUDA libraries for GPU support, adds the app to Windows startup, and launches it immediately.

### Manual install

```bat
pip install -r requirements.txt
```

For NVIDIA GPU acceleration (skip if you already have CUDA Toolkit installed):

```bat
pip install --no-cache-dir -r requirements-windows-gpu.txt
```

### Running

| Method | Use case |
|--------|----------|
| `launchers\windows\WhisperDictation.vbs` | Normal use — silent, no console window |
| `launchers\windows\start_dictation.bat` | Debugging — shows console output |

To start automatically on login, copy `WhisperDictation.vbs` to your startup folder:

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```

---

## Standalone executable (no Python required)

A pre-built Windows executable can be produced with PyInstaller. The resulting folder runs on any Windows 10/11 machine without Python or pip installed.

### Build

```bat
pip install pyinstaller
pyinstaller -y whisper_dictation.spec
```

Output: `dist\WhisperDictation\WhisperDictation.exe` (~260 MB folder)

### Distribute

Zip the entire `dist\WhisperDictation\` folder and copy it to the target machine. Run `WhisperDictation.exe` directly — no installer needed.

### Notes

- The Whisper model (~460 MB) is **not** bundled. It downloads automatically on first run and caches in `%USERPROFILE%\.cache\huggingface\hub\`.
- CUDA DLLs are **not** bundled (would add ~1.2 GB). GPU acceleration works if the target machine has CUDA Toolkit 12.x installed system-wide. Without it the app falls back to CPU silently.
- The log file (`whisper_dictate.log`) is written next to `WhisperDictation.exe`.
- To add to Windows startup, place a shortcut to `WhisperDictation.exe` in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`.

---

## Usage

1. Press `Ctrl+Alt+R` — the tray icon turns red and you hear a high beep
2. Speak
3. Press `Ctrl+Alt+R` again — you hear a low beep, transcription runs, text is pasted

The log file at `whisper_dictate.log` records every transcription session.

---

## Configuration

Edit the constants at the top of `whisper_dictate.py`:

```python
MODEL_SIZE     = "small"          # tiny | base | small | medium | large-v2
POLL_INTERVAL  = 0.05             # hotkey polling interval in seconds
DEBOUNCE_S     = 0.4              # min seconds between two triggers
ALLOWED_LANGS  = {"en", "sk"}     # constrain language detection
INITIAL_PROMPT = "Toto je prepis. This is a transcription."
```

### Model sizes

| Model | VRAM | Speed (GPU) | Accuracy |
|-------|------|-------------|----------|
| tiny | ~200 MB | Very fast | Low |
| base | ~300 MB | Fast | Fair |
| small | ~500 MB | Fast | Good |
| medium | ~1.5 GB | Moderate | Better |
| large-v2 | ~3 GB | Slow | Best |

`small` is the default and fits on most laptop GPUs.

---

## How it works

### Hotkey detection

Uses `GetAsyncKeyState` polling (Windows API) in a background thread. This was chosen over `keyboard` library hooks and `RegisterHotKey` because both of those require a Windows message pump that is not available in `pythonw.exe` (headless Python process).

### CUDA setup

CUDA Toolkit is not required. The `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`, and `nvidia-cuda-runtime-cu12` pip packages provide the required DLLs. `os.add_dll_directory()` is called at startup to make them discoverable by `ctranslate2` before the model loads.

### Language constraint

Whisper's auto-detection can confuse Slovak with Russian, Croatian, or Czech. A two-pass strategy is used: the first pass detects the language, and if the result is not in `ALLOWED_LANGS`, the code picks whichever allowed language had the highest probability score and re-transcribes with it forced.

### Paste

Text is copied to the clipboard with `pyperclip`, then `keybd_event` sends `Ctrl+V`. Before sending, the code waits for all hotkey modifier keys to physically release (otherwise `Ctrl+Shift` still held sends `Ctrl+Shift+V`). The target window handle is captured at stop time and restored via `SetForegroundWindow` before pasting, so focus shifts during CPU transcription do not misdirect the paste.

---

## Project structure

```
whisper-dictate/
├── whisper_dictate.py              Main script
├── whisper_dictation.spec          PyInstaller build spec
├── requirements.txt                Core dependencies
├── requirements-windows-gpu.txt    NVIDIA GPU libraries (Windows)
├── launchers/
│   ├── windows/
│   │   ├── WhisperDictation.vbs    Silent launcher (startup-ready)
│   │   ├── start_dictation.bat     Console launcher (debugging)
│   │   └── install.bat             One-step installer
│   ├── linux/
│   │   └── README.md               Implementation notes
│   └── macos/
│       └── README.md               Implementation notes
├── CLAUDE.md                       Developer notes and gotchas
├── LICENSE
└── .gitignore
```

---

## Contributing

Pull requests for Linux and macOS launchers are welcome. See the platform-specific READMEs in `launchers/` for implementation guidance.

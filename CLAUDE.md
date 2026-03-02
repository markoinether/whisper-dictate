# Whisper Dictation — Project Notes for Claude

## What this is
A Windows background app that transcribes speech to text via OpenAI Whisper (faster-whisper)
and pastes the result into whatever window is in focus.

**Hotkey:** `Ctrl+Alt+R` (toggle: press once to start recording, press again to stop + paste)
**Languages:** Auto-detect, constrained to English and Slovak only
**Model:** `small` on GPU (float16), falls back to CPU (int8) if CUDA unavailable

---

## File layout
```
whisper-dictate/
  whisper_dictate.py        ← main script
  whisper_dictation.spec    ← PyInstaller build spec
  WhisperDictation.vbs      ← silent launcher (use this for startup / normal use)
  start_dictation.bat       ← visible console launcher (use for debugging)
  whisper_dictate.log       ← runtime log (created on launch, overwritten each run)
  CLAUDE.md                 ← this file
  dist/WhisperDictation/    ← built exe output (gitignored)
```

**Startup folder entry:**
`C:\Users\4regs\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\WhisperDictation.vbs`

---

## System info
- OS: Windows 11 Pro
- Python: 3.11.9 at `C:\Users\4regs\AppData\Local\Programs\Python\Python311\`
- GPU: NVIDIA GeForce RTX 3050 Ti Laptop (4 GB VRAM), driver 581.95
- CUDA: **not** installed system-wide; provided via pip packages instead (see below)

---

## Dependencies (all pip-installed)
```
faster-whisper      — Whisper inference via CTranslate2
sounddevice         — microphone capture
soundfile           — WAV file write for temp audio
numpy               — audio array handling
keyboard            — used only for keybd_event paste (NOT for hotkey detection)
pyperclip           — clipboard copy
pystray             — system tray icon
pillow              — icon image generation for pystray
psutil              — single-instance enforcement
nvidia-cublas-cu12  — CUDA cuBLAS DLL (replaces need for full CUDA Toolkit)
nvidia-cudnn-cu12   — CUDA cuDNN DLL
nvidia-cuda-runtime-cu12 — CUDA runtime DLL
```

---

## Architecture decisions

### Hotkey detection: GetAsyncKeyState polling
**Why not `keyboard` library hooks?**
`keyboard` uses `SetWindowsHookEx(WH_KEYBOARD_LL)`. The hook callback requires the installing
thread to pump Windows messages. In `pythonw.exe` (no console) this silently fails — the hook
installs, no error is thrown, but keypresses never arrive.

**Why not `RegisterHotKey` API?**
Also tried. Registered successfully (no error) but `GetMessageA` never received `WM_HOTKEY`
from `pythonw.exe`. Same root cause — no message pump.

**Solution:** Poll `GetAsyncKeyState` every 50ms in a daemon thread. Works in any process,
no admin required, no message pump needed. Debounce of 0.4s prevents double-fire.

### CUDA loading: pip packages + os.add_dll_directory
CUDA Toolkit is not installed system-wide. `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`, and
`nvidia-cuda-runtime-cu12` pip packages provide the required DLLs at:
```
site-packages/nvidia/cublas/bin/cublas64_12.dll
site-packages/nvidia/cudnn/bin/cudnn64_9.dll
site-packages/nvidia/cuda_runtime/bin/cudart64_12.dll
```
`_add_cuda_dll_dirs()` runs before `from faster_whisper import WhisperModel` and calls
`os.add_dll_directory()` on each found path. Without this, ctranslate2 loads fine but
crashes at first inference with `RuntimeError: Library cublas64_12.dll is not found`.

### Paste: keybd_event (not SendInput)
`SendInput` was tried first but the custom ctypes INPUT struct had an incorrect union size
(missing MOUSEINPUT/HARDWAREINPUT members), causing garbage data and silent failure.
`keybd_event` (deprecated but reliable) works correctly with no struct complexity.

Before sending Ctrl+V, the code waits up to 2s for Ctrl/Alt/R to physically release,
then calls `user32.SetForegroundWindow(target_hwnd)` to restore focus to the window that
was active when the stop hotkey was pressed (transcription takes several seconds on CPU,
during which focus can shift).

### Language constraint: two-pass transcription
`faster-whisper` auto-detect can mis-identify Slovak as Russian, Croatian (hr), or Czech.
First pass runs with `language=None`. If `info.language` is not `en` or `sk`, the code
reads `info.all_language_probs`, picks whichever of `en`/`sk` scored higher, and
re-transcribes with that language forced. Second pass only fires on a wrong detection.

### Single-instance enforcement: psutil with normcase
`kill_existing_instances()` runs before everything else (before the log redirect).
Path comparison uses `os.path.normcase()` on both sides — critical on Windows where
paths are case-insensitive and slashes vary. Without normcase, `D:\git\...` does not
match `d:\git\...`, and multiple instances accumulate.
After `proc.kill()`, `proc.wait(timeout=3)` blocks until the old process is actually gone
before the new instance continues startup.

### Log redirect: UTF-8 explicit
When launched via `pythonw.exe`, `sys.stdout` is `None`. The log file must be opened with
`encoding="utf-8"` explicitly — the default cp1252 on Windows cannot encode `●` or `◼`,
causing a `UnicodeEncodeError` that crashes the hotkey thread on first keypress with no
visible error.

### Startup noise suppression
`CT2_VERBOSE=0` env var set before importing faster-whisper suppresses ctranslate2/CUDA
initialization output. `start_dictation.bat` uses `2>nul` to discard any remaining
C-library stderr noise.

---

## Gotchas and things to avoid

| # | Gotcha | Fix |
|---|--------|-----|
| 1 | `keyboard.add_hotkey` silently does nothing in `pythonw.exe` | Use `GetAsyncKeyState` polling |
| 2 | `RegisterHotKey` + `GetMessageA` also fails in `pythonw.exe` | Same — use polling |
| 3 | `ctranslate2` loads on GPU fine but crashes at first inference with cublas error | CUDA DLLs not in search path; call `os.add_dll_directory()` before import |
| 4 | `SendInput` struct — union size wrong (only `ki` member, missing `mi`/`hi`) | Use `keybd_event` instead |
| 5 | Paste sends `Ctrl+Shift+V` not `Ctrl+V` | Wait for modifier keys to release before sending |
| 6 | Target window loses focus during CPU transcription (several seconds) | Capture `GetForegroundWindow()` at stop time; restore before paste |
| 7 | Log file UnicodeEncodeError on `●`/`◼` crashes hotkey thread silently | Open log with `encoding="utf-8"` |
| 8 | Slovak detected as Russian/Croatian/Czech | Two-pass: force `en`/`sk` if auto-detect picks something else |
| 9 | `kill_existing_instances` path match fails on Windows (case, slashes, relative paths) | Use `os.path.normcase()` on both sides AND match on basename — when launched via bat as `python whisper_dictate.py`, the cmdline stores only the bare filename, not the full path |
| 10 | `Ctrl+Alt+Space` intercepted by PowerToys Run before script sees it | Changed hotkey to `Ctrl+Alt+R` |
| 11 | `Win+H` cannot be intercepted by Python at all | Windows kernel-level; not possible without AHK |
| 12 | `suppress=True` on `keyboard.add_hotkey` may need admin rights | Avoided by switching away from keyboard library for detection |
| 13 | Multiple blank lines in console after "Ready" | ctranslate2 CUDA init noise; fix with `CT2_VERBOSE=0` + `2>nul` in bat |
| 14 | nvidia-cudnn pip download corrupts on first try (hash mismatch) | Re-run with `--no-cache-dir` |

---

## Configuration (top of whisper_dictate.py)
```python
MODEL_SIZE    = "small"     # tiny | base | small | medium | large-v2
POLL_INTERVAL = 0.05        # hotkey check interval in seconds
DEBOUNCE_S    = 0.4         # min seconds between two trigger events
ALLOWED_LANGS = {"en", "sk"}
INITIAL_PROMPT = "Toto je prepis. This is a transcription."
```
To upgrade accuracy (at the cost of speed): change `MODEL_SIZE` to `"medium"`.

---

## PyInstaller exe build

Build command (run from repo root, requires `pip install pyinstaller`):
```bat
pyinstaller -y whisper_dictation.spec
```
Output: `dist\WhisperDictation\WhisperDictation.exe` (~260 MB onedir bundle)

**What the spec does:**
- `collect_all()` for `faster_whisper`, `ctranslate2`, `tokenizers`, `huggingface_hub`, `av`
- `console=False` — no window (equivalent to pythonw)
- Excludes `nvidia` CUDA packages (~1.2 GB), `torch`, `tensorflow`
- UPX compression enabled

**Frozen-exe specifics in whisper_dictate.py:**
- `_SCRIPT_DIR` uses `sys.executable` (not `__file__`) when `sys.frozen` is True — `__file__` resolves to a temp extraction path inside the exe, not the exe's actual directory
- `kill_existing_instances()` branches on `sys.frozen`: frozen → match other processes by `proc.info["exe"]` path; script → match by cmdline as before
- Log file lands next to `WhisperDictation.exe` in the dist folder

**Whisper model not bundled** — downloads on first run to `%USERPROFILE%\.cache\huggingface\hub\` (~460 MB). Subsequent runs load from cache instantly.

**CUDA in the exe** — nvidia-* pip DLLs are excluded from the bundle. GPU works if CUDA Toolkit 12.x is installed system-wide on the target PC. Without it, falls back to CPU.

---

## Known limitations
- GPU transcription requires the three nvidia-* pip packages (not system CUDA Toolkit).
  If those are uninstalled, the script falls back to CPU automatically.
- Paste will not work if the target window is an elevated (UAC-elevated) process,
  because `keybd_event` from a non-elevated process cannot send to elevated windows.
- `SetForegroundWindow` can be blocked by Windows if another app has set the foreground
  lock. In that case the paste still fires but may go to the wrong window.

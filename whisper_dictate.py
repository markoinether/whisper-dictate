#!/usr/bin/env python3
"""
Whisper Dictation
-----------------
Press Ctrl+Alt+R to start recording.
Press Ctrl+Alt+R again to stop — text is transcribed and pasted
into whichever window was in focus.

Languages: auto-detect (English / Slovak)
Model:     small
"""

import os
import sys
import time
import threading
import tempfile
import ctypes
import ctypes.wintypes
import winsound
import psutil

# Resolve the directory that contains this script (or exe when frozen by PyInstaller)
if getattr(sys, "frozen", False):
    _SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def kill_existing_instances():
    current_pid = os.getpid()
    to_kill     = []

    if getattr(sys, "frozen", False):
        # Running as a PyInstaller exe — match by exe path
        our_exe = os.path.normcase(sys.executable)
        for proc in psutil.process_iter(["pid", "exe"]):
            try:
                if proc.pid == current_pid:
                    continue
                if os.path.normcase(proc.info["exe"] or "") == our_exe:
                    to_kill.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    else:
        # Running as a Python script — match by script name in cmdline.
        # When launched via bat as `python whisper_dictate.py`, the cmdline
        # stores only the bare filename, so match on both full path and basename.
        script_full = os.path.normcase(os.path.abspath(__file__))
        script_name = os.path.basename(script_full)   # "whisper_dictate.py"

        def _is_our_script(cmdline):
            for arg in cmdline:
                n = os.path.normcase(arg)
                if script_full in n or n.endswith(script_name):
                    return True
            return False

        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.pid == current_pid:
                    continue
                if proc.info["name"] in ("python.exe", "pythonw.exe"):
                    if _is_our_script(proc.info["cmdline"] or []):
                        to_kill.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    for proc in to_kill:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired, psutil.AccessDenied):
            pass

    if to_kill:
        time.sleep(0.3)   # let audio device and OS handles release

    return len(to_kill)


kill_existing_instances()   # runs before anything else, including log redirect
if sys.stdout is None or not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
    _log = open(os.path.join(_SCRIPT_DIR, "whisper_dictate.log"), "w", buffering=1, encoding="utf-8")
    sys.stdout = _log
    sys.stderr = _log

import pyperclip
import sounddevice as sd
import soundfile as sf
import numpy as np
import pystray
import site
from PIL import Image, ImageDraw

# Add CUDA DLL directories so ctranslate2 can find cublas/cudnn.
# Covers both pip-installed nvidia-* packages and system CUDA Toolkit.
def _add_cuda_dll_dirs():
    import glob
    candidates = []
    # pip-installed nvidia-* packages (nvidia-cublas-cu12, nvidia-cudnn-cu12, etc.)
    for sp in site.getsitepackages():
        for pkg in ("cublas", "cudnn", "cuda_runtime", "cufft", "curand"):
            p = os.path.join(sp, "nvidia", pkg, "bin")
            if os.path.exists(p):
                candidates.append(p)
    # System CUDA Toolkit
    for pattern in [
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12*\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11*\bin",
    ]:
        candidates.extend(sorted(glob.glob(pattern)))
    for d in candidates:
        try:
            os.add_dll_directory(d)
        except OSError:
            pass

_add_cuda_dll_dirs()

os.environ.setdefault("CT2_VERBOSE", "0")    # suppress ctranslate2/CUDA init noise
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")  # suppress any TF noise

from faster_whisper import WhisperModel

# ── Configuration ─────────────────────────────────────────────────────────────

MODEL_SIZE    = "small"
SAMPLE_RATE   = 16000
CHANNELS      = 1
POLL_INTERVAL = 0.05
DEBOUNCE_S    = 0.4

INITIAL_PROMPT  = "Toto je prepis. This is a transcription."
ALLOWED_LANGS   = {"en", "sk"}

VK_CONTROL = 0x11
VK_ALT     = 0x12
VK_R       = 0x52

# ──────────────────────────────────────────────────────────────────────────────

recording    = False
audio_frames = []
_lock        = threading.Lock()
model        = None
user32       = ctypes.windll.user32
tray         = None


# ── Tray icon ─────────────────────────────────────────────────────────────────

def _make_icon(color, dot_color=None):
    """Draw a 64×64 circle icon. Optional small dot for recording indicator."""
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=color)
    if dot_color:
        draw.ellipse([20, 20, 44, 44], fill=dot_color)
    return img

ICON_IDLE      = _make_icon((80, 80, 80))          # dark grey  = idle
ICON_RECORDING = _make_icon((200, 30, 30), (255, 80, 80))  # red = recording


def set_tray_state(is_recording):
    if tray is None:
        return
    if is_recording:
        tray.icon  = ICON_RECORDING
        tray.title = "Whisper — RECORDING"
    else:
        tray.icon  = ICON_IDLE
        tray.title = "Whisper Dictation — Ready"


def build_tray():
    global tray
    menu = pystray.Menu(
        pystray.MenuItem("Quit", lambda icon, item: icon.stop())
    )
    tray = pystray.Icon("WhisperDictation", ICON_IDLE, "Whisper Dictation — Ready", menu)
    tray.run()          # blocks; runs on its own thread


# ── Audio & transcription ──────────────────────────────────────────────────────

def audio_callback(indata, frames, time_info, status):
    with _lock:
        if recording:
            audio_frames.append(indata.copy())


def start_recording():
    global recording, audio_frames
    with _lock:
        audio_frames = []
        recording    = True
    set_tray_state(True)
    winsound.Beep(880, 120)   # high beep = started
    print("Recording started (Ctrl+Alt+R to stop)", flush=True)


def stop_and_transcribe(target_hwnd):
    global recording

    with _lock:
        recording = False
        frames    = list(audio_frames)

    set_tray_state(False)
    winsound.Beep(440, 120)   # low beep = stopped

    if not frames:
        print("No audio captured.", flush=True)
        return

    print("Transcribing...", flush=True)
    audio = np.concatenate(frames, axis=0).flatten().astype(np.float32)

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
        sf.write(tmp, audio, SAMPLE_RATE)

        segments, info = model.transcribe(
            tmp,
            language=None,
            initial_prompt=INITIAL_PROMPT,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(seg.text for seg in segments).strip()

        # If Whisper picked a language other than EN or SK, re-transcribe
        # forcing whichever of EN/SK had the higher probability.
        if info.language not in ALLOWED_LANGS:
            probs   = dict(info.all_language_probs or [])
            forced  = "sk" if probs.get("sk", 0) >= probs.get("en", 0) else "en"
            print(f"Detected '{info.language}', forcing '{forced}'", flush=True)
            segments, info = model.transcribe(
                tmp,
                language=forced,
                initial_prompt=INITIAL_PROMPT,
                beam_size=5,
                vad_filter=True,
            )
            text = " ".join(seg.text for seg in segments).strip()

    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)

    if not text:
        print("(nothing transcribed)", flush=True)
        return

    print(f"[{info.language}] {text}", flush=True)
    pyperclip.copy(text)

    # Wait for modifier keys to physically release
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not (key_down(VK_CONTROL) or key_down(VK_ALT) or key_down(VK_R)):
            break
        time.sleep(0.05)
    time.sleep(0.05)

    # Restore focus to the window that was active when recording stopped
    if target_hwnd:
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.05)

    _send_ctrl_v()


# ── Helpers ───────────────────────────────────────────────────────────────────

def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def combo_pressed():
    return key_down(VK_CONTROL) and key_down(VK_ALT) and key_down(VK_R)


def _cuda_available():
    for dll in ("cublas64_12.dll", "cublas64_11.dll"):
        try:
            ctypes.WinDLL(dll)
            return True
        except OSError:
            pass
    return False


def _send_ctrl_v():
    KEYEVENTF_KEYUP = 0x0002
    VK_V            = 0x56
    kbe = ctypes.windll.user32.keybd_event
    kbe(VK_CONTROL, 0, 0,              0)
    kbe(VK_V,       0, 0,              0)
    kbe(VK_V,       0, KEYEVENTF_KEYUP, 0)
    kbe(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def on_hotkey():
    global recording
    if not recording:
        start_recording()
    else:
        # Capture focused window now — before transcription delay moves focus
        hwnd = user32.GetForegroundWindow()
        threading.Thread(target=stop_and_transcribe, args=(hwnd,), daemon=True).start()


def load_model():
    global model
    if _cuda_available():
        print(f"CUDA found. Loading '{MODEL_SIZE}' on GPU...", flush=True)
        try:
            model = WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")
            print("GPU ready.", flush=True)
            return
        except Exception as e:
            print(f"GPU load failed ({e}), falling back to CPU...", flush=True)
    else:
        print(f"CUDA not found. Loading '{MODEL_SIZE}' on CPU...", flush=True)

    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    print("CPU ready.", flush=True)


def hotkey_loop():
    was_down     = False
    last_trigger = 0.0
    while True:
        down = combo_pressed()
        now  = time.time()
        if down and not was_down and (now - last_trigger) >= DEBOUNCE_S:
            last_trigger = now
            try:
                on_hotkey()
            except Exception as e:
                print(f"Error: {e}", flush=True)
        was_down = down
        time.sleep(POLL_INTERVAL)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    load_model()

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        callback=audio_callback,
    )
    stream.start()

    threading.Thread(target=hotkey_loop, daemon=True).start()
    threading.Thread(target=build_tray,  daemon=True).start()

    print("Ready. Ctrl+Alt+R to start/stop.\n", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        stream.close()
        print("Bye.", flush=True)


if __name__ == "__main__":
    main()

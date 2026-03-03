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
import site
import time
import threading
import traceback
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
import numpy as np
import pystray
from PIL import Image, ImageDraw

# Add CUDA DLL directories so ctranslate2 can find cublas/cudnn.
# Covers both pip-installed nvidia-* packages and system CUDA Toolkit.
#
# IMPORTANT: In a PyInstaller frozen exe, site.getsitepackages() returns paths
# relative to the exe (not the real Python install), so we also scan common
# Windows Python user-install locations explicitly.
def _add_cuda_dll_dirs():
    import glob
    search_roots = []

    # Works in script mode; returns wrong paths when frozen.
    try:
        search_roots.extend(site.getsitepackages())
    except Exception:
        pass

    # Frozen exe: scan the actual user Python install under LOCALAPPDATA.
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        for py_dir in glob.glob(
            os.path.join(localappdata, "Programs", "Python", "Python3*")
        ):
            search_roots.append(os.path.join(py_dir, "Lib", "site-packages"))

    # pip-installed nvidia-* packages (nvidia-cublas-cu12, nvidia-cudnn-cu12, etc.)
    for sp in search_roots:
        for pkg in ("cublas", "cudnn", "cuda_runtime", "cufft", "curand"):
            p = os.path.join(sp, "nvidia", pkg, "bin")
            if os.path.exists(p):
                try:
                    os.add_dll_directory(p)
                except OSError:
                    pass

    # System CUDA Toolkit
    for pattern in [
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12*\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11*\bin",
    ]:
        for d in sorted(glob.glob(pattern)):
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

INITIAL_PROMPT = "Toto je prepis. This is a transcription."
ALLOWED_LANGS  = {"en", "sk"}

# Whisper commonly hallucinates these phrases on silence or very short audio.
# Any transcription that matches one of these exactly (case-insensitive) is discarded.
HALLUCINATIONS = {
    ".", "..", "...",
    "thank you.", "thanks for watching.", "thank you for watching.",
    "thanks for watching", "thank you for watching",
    "please subscribe.", "like and subscribe.",
    "subtitles by", "subtitles by the amara.org community",
    "you", "you.", "bye.", "bye-bye.",
    "this video is brought to you by",
}

VK_CONTROL = 0x11
VK_ALT     = 0x12
VK_R       = 0x52

# ──────────────────────────────────────────────────────────────────────────────

# Thread-safe state flags
_recording    = threading.Event()  # set while recording audio
_transcribing = threading.Event()  # set while transcription thread is running

# Audio buffer — written by the sounddevice callback, read by the transcription thread
_audio_chunks: list = []
_audio_lock = threading.Lock()

model  = None
user32 = ctypes.windll.user32
tray   = None


# ── Tray icon ─────────────────────────────────────────────────────────────────

def _make_icon(color, dot_color=None):
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=color)
    if dot_color:
        draw.ellipse([20, 20, 44, 44], fill=dot_color)
    return img

ICON_IDLE      = _make_icon((80, 80, 80))
ICON_RECORDING = _make_icon((200, 30, 30), (255, 80, 80))


def set_tray_state(is_recording: bool):
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
    menu = pystray.Menu(pystray.MenuItem("Quit", lambda icon, item: icon.stop()))
    tray = pystray.Icon("WhisperDictation", ICON_IDLE, "Whisper Dictation — Ready", menu)
    tray.run()          # blocks until icon.stop() is called


# ── Audio & transcription ──────────────────────────────────────────────────────

def audio_callback(indata, frames, time_info, status):
    if _recording.is_set():
        with _audio_lock:
            _audio_chunks.append(indata.copy())


def start_recording():
    with _audio_lock:
        _audio_chunks.clear()
    _recording.set()
    set_tray_state(True)
    winsound.Beep(880, 120)   # high beep = started
    print("Recording started", flush=True)


def _transcribe_audio(audio: np.ndarray, language=None):
    """Run faster-whisper on a float32 numpy array. Returns (text, info)."""
    segments, info = model.transcribe(
        audio,
        language=language,
        initial_prompt=INITIAL_PROMPT,
        beam_size=5,
        vad_filter=True,
    )
    text = " ".join(seg.text for seg in segments).strip()
    return text, info


def stop_and_transcribe(target_hwnd):
    _recording.clear()
    _transcribing.set()
    try:
        with _audio_lock:
            chunks = list(_audio_chunks)

        set_tray_state(False)
        winsound.Beep(440, 120)   # low beep = stopped

        if not chunks:
            print("No audio captured.", flush=True)
            return

        print("Transcribing...", flush=True)
        audio = np.concatenate(chunks, axis=0).flatten().astype(np.float32)

        # Pass numpy array directly — no temp file needed
        text, info = _transcribe_audio(audio)

        # If Whisper picked a language outside EN/SK, re-transcribe with the
        # better-scoring allowed language forced.
        if info.language not in ALLOWED_LANGS:
            probs  = dict(info.all_language_probs or [])
            forced = "sk" if probs.get("sk", 0) >= probs.get("en", 0) else "en"
            print(f"Detected '{info.language}', forcing '{forced}'", flush=True)
            text, info = _transcribe_audio(audio, language=forced)

        if not text:
            print("(nothing transcribed)", flush=True)
            return

        if text.lower() in HALLUCINATIONS:
            print(f"(hallucination filtered: {text!r})", flush=True)
            return

        print(f"[{info.language}] {text}", flush=True)
        pyperclip.copy(text)

        # Wait for modifier keys to physically release (up to 2 s)
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

    except Exception as e:
        print(f"Transcription error: {e}", flush=True)
        traceback.print_exc()
    finally:
        _transcribing.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def combo_pressed() -> bool:
    return key_down(VK_CONTROL) and key_down(VK_ALT) and key_down(VK_R)


def _cuda_available() -> bool:
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
    kbe = user32.keybd_event
    kbe(VK_CONTROL, 0, 0,               0)
    kbe(VK_V,       0, 0,               0)
    kbe(VK_V,       0, KEYEVENTF_KEYUP, 0)
    kbe(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def on_hotkey():
    if _recording.is_set():
        # Capture focused window now — before transcription delay moves focus
        hwnd = user32.GetForegroundWindow()
        threading.Thread(target=stop_and_transcribe, args=(hwnd,), daemon=True).start()
    elif _transcribing.is_set():
        print("Still transcribing, ignoring.", flush=True)
    else:
        start_recording()


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
                print(f"Hotkey error: {e}", flush=True)
        was_down = down
        time.sleep(POLL_INTERVAL)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    load_model()

    # blocksize=2048 → ~8 callbacks/sec instead of ~60 with the default 256-sample block.
    # Fewer GIL acquisitions from the audio thread = less jitter for Bluetooth HID devices.
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=2048,
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
        if tray is not None:
            tray.stop()
        print("Bye.", flush=True)


if __name__ == "__main__":
    main()

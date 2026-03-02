# macOS launcher (planned)

macOS support is not yet implemented. Contributions welcome.

## Expected differences from Windows

| Feature | Windows (current) | macOS (planned) |
|---------|------------------|-----------------|
| Hotkey detection | `GetAsyncKeyState` polling | `pynput` global listener |
| Paste | `keybd_event` + `SetForegroundWindow` | `osascript` or `pyautogui` |
| System tray | `pystray` (Win32 backend) | `pystray` (rumps or PyObjC backend) |
| Silent launch | VBS + pythonw | `launchd` plist or Login Items |
| GPU | NVIDIA CUDA | Apple Metal (via `mlx-whisper` or CoreML) |

## Notes

- macOS requires granting **Accessibility** and **Microphone** permissions to Terminal / the app.
- For Apple Silicon (M1/M2/M3), consider `mlx-whisper` instead of `faster-whisper` for native Metal acceleration.

## Dependencies (macOS, approximate)

```bash
brew install python portaudio
pip install -r ../../requirements.txt
```

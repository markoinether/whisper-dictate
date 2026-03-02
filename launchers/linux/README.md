# Linux launcher (planned)

Linux support is not yet implemented. Contributions welcome.

## Expected differences from Windows

| Feature | Windows (current) | Linux (planned) |
|---------|------------------|-----------------|
| Hotkey detection | `GetAsyncKeyState` polling | `evdev` or `pynput` |
| Paste | `keybd_event` + `SetForegroundWindow` | `xdotool` or `ydotool` (Wayland) |
| System tray | `pystray` (Win32 backend) | `pystray` (AppIndicator/GTK backend) |
| Silent launch | `pythonw.exe` + VBS | systemd user service or `.desktop` autostart |
| CUDA | pip `nvidia-*` packages | CUDA Toolkit or pip packages |

## Dependencies (Linux, approximate)

```bash
sudo apt install python3 python3-pip ffmpeg
pip install -r ../../requirements.txt
# For Wayland paste support:
sudo apt install ydotool
# For X11 paste support:
sudo apt install xdotool
```

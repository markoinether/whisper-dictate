' Whisper Dictation — silent launcher (no console window)
' Uses pythonw.exe from PATH; derives script path from this file's location.

Dim shell, fso, repoRoot, pythonScript

Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

' launchers\windows\ -> launchers\ -> repo root
repoRoot     = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
pythonScript = repoRoot & "\whisper_dictate.py"

shell.Run "pythonw """ & pythonScript & """", 0, False

Set shell = Nothing
Set fso   = Nothing

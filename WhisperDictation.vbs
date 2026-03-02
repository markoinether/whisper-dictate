' Whisper Dictation — silent launcher (no console window)
' Uses pythonw.exe from PATH; derives script path from this file's location.

Dim shell, fso, scriptDir, pythonScript

Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

scriptDir    = fso.GetParentFolderName(WScript.ScriptFullName)
pythonScript = scriptDir & "\whisper_dictate.py"

shell.Run "pythonw """ & pythonScript & """", 0, False

Set shell = Nothing
Set fso   = Nothing

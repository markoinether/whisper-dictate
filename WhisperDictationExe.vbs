' Whisper Dictation — launches the compiled exe (dist\WhisperDictation\WhisperDictation.exe)
' Use this for startup / normal use once the exe is built.
' Shows as "WhisperDictation" in Task Manager (not pythonw.exe).

Dim shell, fso, scriptDir, exePath

Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
exePath   = scriptDir & "\dist\WhisperDictation\WhisperDictation.exe"

shell.Run """" & exePath & """", 0, False

Set shell = Nothing
Set fso   = Nothing

' Minta Silent Starter — double-click to run Minta in background
' No terminal window. No admin required.
' Put a shortcut of this file in your Startup folder for auto-start:
'   Win+R → shell:startup → paste shortcut

Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Start-Minta.vbs is at the repo root. Use its own directory as rootDir.
rootDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

WshShell.Run "pythonw """ & rootDir & "\minta_cli.py"" start", 0, False

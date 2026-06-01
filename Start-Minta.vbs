' Minta Silent Starter — double-click to run Minta in background
' No terminal window. No admin required.
' Put a shortcut of this file in your Startup folder for auto-start:
'   Win+R → shell:startup → paste shortcut

Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
rootDir = objFSO.GetParentFolderName(scriptDir)

WshShell.Run "pythonw """ & rootDir & "\minta_cli.py"" start", 0, False

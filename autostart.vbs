Set objFSO = CreateObject("Scripting.FileSystemObject")
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\autostart.bat"
CreateObject("Wscript.Shell").Run Chr(34) & batPath & Chr(34), 0, False

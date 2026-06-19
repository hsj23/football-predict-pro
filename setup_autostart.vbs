Set WshShell = CreateObject("WScript.Shell")
Set Shortcut = WshShell.CreateShortcut(WshShell.SpecialFolders("Startup") & "\FootballPredict.lnk")
Shortcut.TargetPath = "D:\小黄的助手\足彩预测系统\autostart.vbs"
Shortcut.WorkingDirectory = "D:\小黄的助手\足彩预测系统"
Shortcut.WindowStyle = 7
Shortcut.Description = "FootballPredict AutoStart"
Shortcut.Save()
MsgBox "AutoStart setup complete! Shortcut added to Startup folder.", vbInformation, "FootballPredict"

$ScriptDir = $PSScriptRoot
$StartupDir = [Environment]::GetFolderPath('Startup')

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$StartupDir\FootballPredict.lnk")
$Shortcut.TargetPath = Join-Path $ScriptDir 'autostart.vbs'
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.WindowStyle = 7
$Shortcut.Description = 'FootballPredict AutoStart'
$Shortcut.Save()

Write-Host "Autostart shortcut created: $StartupDir\FootballPredict.lnk"

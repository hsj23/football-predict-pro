$ScriptDir = $PSScriptRoot
$Desktop = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $Desktop '足彩预测系统.lnk'

$WS = New-Object -ComObject WScript.Shell
$SC = $WS.CreateShortcut($ShortcutPath)
$SC.TargetPath = Join-Path $ScriptDir '一键启动.bat'
$SC.WorkingDirectory = $ScriptDir
$SC.Description = '足彩预测系统'
$SC.IconLocation = 'imageres.dll,173'
$SC.Save()

Write-Host "桌面快捷方式已创建: $ShortcutPath"

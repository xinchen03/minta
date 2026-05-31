# Minta Desktop Shortcut Setup — run once, get a desktop icon with logo
# Right-click this file → "Run with PowerShell"

$mintaDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Minta.lnk"
$targetPath = Join-Path $mintaDir "Start-Minta.vbs"
$iconPath = Join-Path $mintaDir "assets\logo.ico"

$WshShell = New-Object -ComObject WScript.Shell
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.IconLocation = $iconPath
$shortcut.WorkingDirectory = $mintaDir
$shortcut.WindowStyle = 7  # Minimized
$shortcut.Description = "Minta — AI Memory Engine"
$shortcut.Save()

Write-Host "Desktop shortcut created: $shortcutPath" -ForegroundColor Green
Write-Host "Icon: $iconPath" -ForegroundColor Green

# Creates "Live Translator" shortcuts (desktop + Start menu) that run "Start Live Translator.bat".
$name = 'Live Translator'
$dir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat  = Join-Path $dir 'Start Live Translator.bat'
$icon = Join-Path $dir 'translator.ico'
if (-not (Test-Path $bat)) { Write-Host "Start Live Translator.bat is missing from $dir"; exit 1 }

$shell = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($place in $places) {
    $link = $shell.CreateShortcut((Join-Path $place "$name.lnk"))
    $link.TargetPath = $env:ComSpec                 # cmd.exe, so the shortcut can be pinned to the taskbar
    $link.Arguments = '/c ""' + $bat + '""'
    $link.WorkingDirectory = $dir
    $link.WindowStyle = 7                           # start minimised: the console stays out of the way
    if (Test-Path $icon) { $link.IconLocation = "$icon,0" }
    $link.Description = 'Live speech subtitles and translation for OBS'
    $link.Save()
    Write-Host "Created: $(Join-Path $place "$name.lnk")"
}

$answer = Read-Host "`nHide the code file (translator_http.py) in this folder so it stays out of the way? (y/n)"
if ($answer -match '^[yY]') {
    $item = Get-Item (Join-Path $dir 'translator_http.py') -Force
    $item.Attributes = $item.Attributes -bor [IO.FileAttributes]::Hidden
    Write-Host 'Hidden. VS Code still shows it; in File Explorer use View > Show > Hidden items to see it again.'
}
Write-Host "`nDone. To pin it: open Start, find '$name', right-click > Pin to Start / Pin to taskbar."

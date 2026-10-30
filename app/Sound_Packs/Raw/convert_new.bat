@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$fx='apad=pad_dur=0.6,highpass=f=300,lowpass=f=3500,aecho=0.8:0.7:40:0.25,acompressor,volume=4.0,alimiter=limit=0.95'; $root=(Get-Location).Path; $out=Join-Path $root 'out'; Get-ChildItem -Path $root -Recurse -Filter *.wav | Where-Object { -not $_.FullName.StartsWith($out + '\') } | ForEach-Object { $rel=$_.FullName.Substring($root.Length+1); $dest=Join-Path $out $rel; if (Test-Path $dest) { return }; New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null; Write-Host ('Converting ' + $rel); & ffmpeg -y -loglevel error -i $_.FullName -af $fx $dest }"
echo Done.
pause
# Deploy EliteMining Plugin to VoiceAttack
# Run this after closing VoiceAttack to update the plugin

Write-Host "Deploying EliteMining Plugin..." -ForegroundColor Cyan

$dllPath = "bin\Release\net48\EliteMiningPlugin.dll"
$vaPath = "D:\SteamLibrary\steamapps\common\VoiceAttack 2\Apps\EliteMining"

# Check if DLL exists
if (!(Test-Path $dllPath)) {
    Write-Host "ERROR: Plugin DLL not found. Run .\build.ps1 first." -ForegroundColor Red
    exit 1
}

# Check if VoiceAttack is running
$vaProcess = Get-Process -Name "VoiceAttack" -ErrorAction SilentlyContinue
if ($vaProcess) {
    Write-Host "ERROR: VoiceAttack is running. Close it first." -ForegroundColor Red
    exit 1
}

# Deploy
try {
    Copy-Item $dllPath $vaPath -Force -ErrorAction Stop
    Write-Host "✓ Deployed to: $vaPath" -ForegroundColor Green
    Write-Host "`nNow start VoiceAttack to load the updated plugin." -ForegroundColor Cyan
} catch {
    Write-Host "ERROR: Failed to copy DLL: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

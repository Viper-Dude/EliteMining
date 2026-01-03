# Build EliteMining VoiceAttack Plugin
# Builds the plugin DLL for VoiceAttack integration

Write-Host "Building EliteMining Plugin..." -ForegroundColor Cyan

# Check if .NET SDK is available
if (!(Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: .NET SDK not found. Please install from https://dotnet.microsoft.com/download" -ForegroundColor Red
    exit 1
}

# Build Release version
Write-Host "`nBuilding Release configuration..." -ForegroundColor Yellow
dotnet build -c Release -v minimal

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✓ Build successful!" -ForegroundColor Green
    Write-Host "`nOutput: bin\Release\net48\EliteMiningPlugin.dll" -ForegroundColor Cyan
    
    # Auto-deploy if VoiceAttack is not running
    $vaPath = "D:\SteamLibrary\steamapps\common\VoiceAttack 2\Apps\EliteMining"
    $vaProcess = Get-Process -Name "VoiceAttack" -ErrorAction SilentlyContinue
    
    if ($vaProcess) {
        Write-Host "`n⚠ VoiceAttack is running. Cannot deploy." -ForegroundColor Yellow
        Write-Host "Close VoiceAttack and run: .\deploy.ps1" -ForegroundColor Yellow
    } else {
        Write-Host "`nDeploying to VoiceAttack..." -ForegroundColor Yellow
        Copy-Item "bin\Release\net48\EliteMiningPlugin.dll" $vaPath -Force
        Write-Host "✓ Deployed to: $vaPath" -ForegroundColor Green
        Write-Host "`nRestart VoiceAttack to load the updated plugin." -ForegroundColor Cyan
    }
} else {
    Write-Host "`n✗ Build failed!" -ForegroundColor Red
    exit 1
}

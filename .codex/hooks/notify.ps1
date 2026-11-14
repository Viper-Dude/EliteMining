param()

$ErrorActionPreference = 'SilentlyContinue'

$stdin = [Console]::In.ReadToEnd()
$message = 'Claude Code needs your attention'
try {
    $payload = $stdin | ConvertFrom-Json
    if ($payload.message) {
        $message = $payload.message
    }
} catch {}

[Console]::Beep(880, 200)
[Console]::Beep(660, 200)
Write-Host "[Claude Code] $message"

exit 0

# Set a user's own permanent password. Shows * for each character typed.
#   powershell -ExecutionPolicy Bypass -File scripts\set_password.ps1 you@example.com           (this computer's database)
#   powershell -ExecutionPolicy Bypass -File scripts\set_password.ps1 you@example.com -Live     (the LIVE site's database)
# -Live reads the live database address from .env.render (never shown) for this run only.
param([Parameter(Mandatory = $true)][string]$Email, [switch]$Live)
Set-Location (Split-Path $PSScriptRoot -Parent)
$where = "this computer"
if ($Live) {
    $line = Get-Content .env.render | Where-Object { $_ -like "SLC_DATABASE_URL=*" } | Select-Object -First 1
    if (-not $line) { Write-Host ".env.render has no SLC_DATABASE_URL line." -ForegroundColor Red; exit 1 }
    $env:SLC_DATABASE_URL = $line.Substring("SLC_DATABASE_URL=".Length).Trim()
    $where = "the LIVE site (slc-sessional-plan.onrender.com)"
}
Write-Host "Set the password for $Email on $where" -ForegroundColor Cyan
Write-Host "At least 10 characters, with upper case, lower case and a digit (e.g. Ruchira2026Slc)." -ForegroundColor Gray
function Read-Secret([string]$prompt) {
    $s = Read-Host -Prompt $prompt -AsSecureString
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}
try {
    while ($true) {
        $a = Read-Secret "New password"
        $b = Read-Secret "Type it again"
        "$a`n$b" | & .\.venv\Scripts\python.exe -m scripts.set_password $Email
        if ($LASTEXITCODE -eq 0) { break }
        Write-Host "Try again." -ForegroundColor Yellow
    }
} finally {
    Remove-Variable a, b -ErrorAction SilentlyContinue
    if ($Live) { Remove-Item Env:SLC_DATABASE_URL -ErrorAction SilentlyContinue }
}
Write-Host "Done. Close this window and sign in on $where." -ForegroundColor Green

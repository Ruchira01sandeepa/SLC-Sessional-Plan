# Set a user's own permanent password. Shows * for each character typed.
#   powershell -ExecutionPolicy Bypass -File scripts\set_password.ps1 you@example.com
param([Parameter(Mandatory = $true)][string]$Email)
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host "Set the password for $Email" -ForegroundColor Cyan
Write-Host "At least 10 characters, with upper case, lower case and a digit (e.g. Ruchira2026Slc)." -ForegroundColor Gray
function Read-Secret([string]$prompt) {
    $s = Read-Host -Prompt $prompt -AsSecureString
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}
while ($true) {
    $a = Read-Secret "New password"
    $b = Read-Secret "Type it again"
    "$a`n$b" | & .\.venv\Scripts\python.exe -m scripts.set_password $Email
    if ($LASTEXITCODE -eq 0) { break }
    Write-Host "Try again." -ForegroundColor Yellow
}
Remove-Variable a, b
Write-Host "Done. Close this window and sign in." -ForegroundColor Green

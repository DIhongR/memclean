# git_push.ps1
# ============================================================
#  Push E:\dsh\gzq\memclean to GitHub.
#
#  Background: Steamcommunity302 (a Steam network tool) hijacks
#  github.com in hosts to 127.0.0.1 and serves it through a local
#  reverse proxy with a self-signed certificate. Git therefore
#  fails with certificate errors unless it trusts that CA.
#
#  The CA has already been exported to _certs\s302_ca.crt and
#  registered in this repo's .git/config (http.sslCAInfo +
#  http.sslVerifyHostname=false), so a plain push just works.
#
#  Usage:  powershell -File git_push.ps1 -Message "what changed"
#          powershell -File git_push.ps1            (message: update)
# ============================================================
param(
    [string]$Message = "update"
)

$ErrorActionPreference = 'Stop'
$Repo = 'E:\dsh\gzq\memclean'

# Make sure git is on PATH (this machine has Git at the default location)
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $env:Path = "$env:Path;$env:ProgramFiles\Git\cmd"
}

Set-Location $Repo

Write-Host "Adding and committing '$Message' ..."
& git add -A
& git commit -m $Message 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "(nothing new to commit)"
}

Write-Host "Pushing to GitHub ..."
& git push
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
    Write-Host "DONE. Pushed to https://github.com/DIHongR/memclean"
    & git log --oneline -1
} else {
    Write-Host "ERROR: push failed with code $code"
    Write-Host "If the error mentions certificates, make sure Steamcommunity302 is"
    Write-Host "running (it must serve github.com) and that _certs\s302_ca.crt exists."
}
exit $code

# git_push_memclean.ps1
# ============================================================
#  Push E:\dsh\gzq\memclean to GitHub while Steamcommunity302 is
#  running. 302 hijacks github.com in hosts with a self-signed
#  certificate, which breaks plain "git push".
#
#  Flow: self-elevate (UAC)
#        -> strip github/#S302 lines from hosts
#        -> git push
#        -> restore hosts (always, even on failure)
#
#  Usage:  powershell -File git_push.ps1 -Message "commit message"
#          (or just double-click it - default message "update")
# ============================================================
param(
    [string]$Message = "update"
)

$ErrorActionPreference = 'Stop'
$Repo   = 'E:\dsh\gzq\memclean'
$Hosts  = "$env:SystemRoot\System32\drivers\etc\hosts"
$Backup = "$env:TEMP\hosts_s302_backup.txt"
$GitExe = Join-Path $env:ProgramFiles 'Git\cmd\git.exe'

function Write-Step($n, $text) { Write-Host "[$n/3] $text" }

# ---- 1. Self-elevate if needed (hosts needs admin) ----
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Need administrator rights (to edit hosts). Requesting elevation..."
    $myPath = $MyInvocation.MyCommand.Path
    Start-Process powershell.exe `
        -Verb RunAs `
        -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$myPath`"",'-Message',"`"$Message`"" `
        -Wait
    Write-Host "Done (elevated instance finished)."
    exit $LASTEXITCODE
}

Set-Location $Repo
if (-not (Test-Path $GitExe)) { $GitExe = 'git' }

# ---- 2. Strip github entries from hosts ----
Write-Step 1 "Removing github entries from hosts..."
Copy-Item -Path $Hosts -Destination $Backup -Force
$lines = Get-Content $Hosts
$keep  = $lines | Where-Object { $_ -notmatch 'github|#S302' }
Set-Content -Path $Hosts -Value $keep -Encoding ASCII
Write-Host ("  removed {0} lines" -f ($lines.Count - $keep.Count))

# ---- 3. Push ----
Write-Step 2 "Pushing to GitHub..."
$pushCode = 0
try {
    & $GitExe add -A
    & $GitExe commit -m $Message 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "  (nothing new to commit)" }
    & $GitExe push
    $pushCode = $LASTEXITCODE
} catch {
    Write-Host ("  push error: " + $_.Exception.Message)
    $pushCode = 1
}

# ---- 4. Always restore hosts ----
Write-Step 3 "Restoring hosts..."
Copy-Item -Path $Backup -Destination $Hosts -Force
Write-Host "  hosts restored"

if ($pushCode -eq 0) {
    Write-Host "`nDONE. Pushed successfully."
} else {
    Write-Host "`nERROR: push failed (code $pushCode)."
}
exit $pushCode

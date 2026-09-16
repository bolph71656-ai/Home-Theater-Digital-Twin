param(
    [string]$ProjectId,
    [string]$ContextId,
    [string]$DataDir
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    Write-Host 'Creating Python 3.12 virtual environment...'
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create Python 3.12 virtual environment.' }
}

Write-Host 'Ensuring native editor dependencies are installed...'
& $Python -m pip install -e '.\backend'
if ($LASTEXITCODE -ne 0) { throw 'Backend installation failed.' }

$LaunchArgs = @('-m', 'htdt.native_editor')
if ($ProjectId) { $LaunchArgs += @('--project-id', $ProjectId) }
if ($ContextId) { $LaunchArgs += @('--context-id', $ContextId) }
if ($DataDir) { $LaunchArgs += @('--data-dir', $DataDir) }

Write-Host 'Starting Home Theater Digital Twin native editor.'
& $Python @LaunchArgs
exit $LASTEXITCODE

param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
    $OutputDir = Join-Path $RepoRoot "dist-native"
}
$WorkRoot = Join-Path $RepoRoot ".tmp\n05-package"
$BuildVenv = Join-Path $WorkRoot "venv"

try {
    if (Test-Path $WorkRoot) {
        Remove-Item -Recurse -Force $WorkRoot
    }
    New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
    py -3.12 -m venv $BuildVenv
    $Python = Join-Path $BuildVenv "Scripts\python.exe"
    & $Python -m pip install --disable-pip-version-check -e "$RepoRoot\backend[package]"
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --windowed `
        --name HTDT `
        --paths "$RepoRoot\backend\src" `
        --collect-all pyvista `
        --collect-all pyvistaqt `
        --distpath $OutputDir `
        --workpath (Join-Path $WorkRoot "build") `
        --specpath $WorkRoot `
        (Join-Path $RepoRoot "scripts\native_entry.py")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    Write-Host "Built native package: $(Join-Path $OutputDir 'HTDT\HTDT.exe')"
}
finally {
    if (Test-Path $WorkRoot) {
        Remove-Item -Recurse -Force $WorkRoot
    }
}

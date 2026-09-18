param(
    [string]$PackageDir = "",
    [string]$OutputDir = "",
    [string]$IsccPath = "",
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not $PackageDir) {
    $PackageDir = Join-Path $RepoRoot "dist-native\HTDT"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $RepoRoot "dist-installer"
}
if (-not $Version) {
    $PyProject = Get-Content (Join-Path $RepoRoot "backend\pyproject.toml") -Raw
    $Match = [regex]::Match($PyProject, '(?m)^version\s*=\s*"([^"]+)"\s*$')
    if (-not $Match.Success) {
        throw "Could not read project version from backend/pyproject.toml"
    }
    $Version = $Match.Groups[1].Value
}
if (-not (Test-Path (Join-Path $PackageDir "HTDT.exe"))) {
    throw "Native package not found: $(Join-Path $PackageDir 'HTDT.exe')"
}
if (-not $IsccPath) {
    $Candidates = @(@(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe")
    ) | Where-Object { $_ -and (Test-Path $_) })
    if ($Candidates.Count -eq 0) {
        $Command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($Command) {
            $IsccPath = $Command.Source
        } else {
            throw "ISCC.exe not found. Install Inno Setup before building the installer."
        }
    } else {
        $IsccPath = $Candidates[0]
    }
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$PackageFull = (Resolve-Path $PackageDir).Path
$InstallerScript = Join-Path $RepoRoot "installer\HTDT.iss"

& $IsccPath `
    "/DAppVersion=$Version" `
    "/DSourceDir=$PackageFull" `
    "/O$OutputDir" `
    $InstallerScript

if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE"
}

$Expected = Join-Path $OutputDir "HTDT-Setup-$Version.exe"
if (-not (Test-Path $Expected)) {
    throw "Installer output missing: $Expected"
}
Write-Host "Built installer: $Expected"

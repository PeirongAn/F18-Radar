[CmdletBinding()]
param(
    [ValidatePattern('^[0-9A-Za-z][0-9A-Za-z._-]*$')]
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$packageJson = Join-Path $repoRoot "package.json"
$pythonExe = Join-Path $repoRoot "server\.venv\Scripts\python.exe"
$buildScript = Join-Path $repoRoot "packaging\build_portable.ps1"

if (-not (Test-Path -LiteralPath $packageJson)) {
    throw "package.json was not found: $packageJson"
}
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python 3.10 environment was not found: $pythonExe"
}
if (-not (Test-Path -LiteralPath $buildScript)) {
    throw "Packaging script was not found: $buildScript"
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "npm.cmd was not found. Install Node.js before building."
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $package = Get-Content -LiteralPath $packageJson -Raw | ConvertFrom-Json
    $Version = [string]$package.version
}
if ($Version -notmatch '^[0-9A-Za-z][0-9A-Za-z._-]*$') {
    throw "Invalid package version: $Version"
}

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "node_modules"))) {
    Write-Host "node_modules is missing; running npm ci..."
    Push-Location $repoRoot
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

& $pythonExe -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($null -eq $uv) {
        throw "PyInstaller is missing. Install uv, then run: uv pip install --python server\.venv\Scripts\python.exe pyinstaller==6.16.0"
    }
    Write-Host "PyInstaller is missing; installing build tool 6.16.0..."
    & $uv.Source pip install --python $pythonExe pyinstaller==6.16.0
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller installation failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Building latest source as version $Version..."
& $buildScript -Version $Version

Write-Host ""
Write-Host "Build completed. Output directory:"
Write-Host (Join-Path $repoRoot "release\F18-Radar-$Version-win-x64")

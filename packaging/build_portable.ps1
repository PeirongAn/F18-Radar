param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9A-Za-z][0-9A-Za-z._-]*$')]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$releaseRoot = Join-Path $repoRoot "release"
$packageName = "F18-Radar-$Version-win-x64"
$packageDir = Join-Path $releaseRoot $packageName
$zipPath = Join-Path $releaseRoot "$packageName.zip"
$checksumPath = "$zipPath.sha256"
$pyinstallerWork = Join-Path $repoRoot "build\pyinstaller-portable"
$pyinstallerDist = Join-Path $repoRoot "build\pyinstaller-dist"
$pythonExe = Join-Path $repoRoot "server\.venv\Scripts\python.exe"
$specFile = Join-Path $PSScriptRoot "F18RadarServer.spec"

foreach ($path in @($packageDir, $zipPath, $checksumPath, $pyinstallerWork, $pyinstallerDist)) {
    $fullPath = [System.IO.Path]::GetFullPath($path)
    if (-not $fullPath.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside repository: $fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

Push-Location $repoRoot
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed with exit code $LASTEXITCODE" }

    & $pythonExe -m PyInstaller --noconfirm --clean --workpath $pyinstallerWork --distpath $pyinstallerDist $specFile
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

    New-Item -ItemType Directory -Force -Path $packageDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $packageDir "config") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $packageDir "data") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $packageDir "logs") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $packageDir "tools") | Out-Null

    Copy-Item -LiteralPath (Join-Path $pyinstallerDist "F18RadarServer") -Destination (Join-Path $packageDir "runtime") -Recurse
    Copy-Item -LiteralPath (Join-Path $repoRoot "dist") -Destination (Join-Path $packageDir "web") -Recurse
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "portable.env") -Destination (Join-Path $packageDir "config\portable.env")
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "open_when_ready.ps1") -Destination (Join-Path $packageDir "tools\open_when_ready.ps1")
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "start_f18_radar.cmd") -Destination (Join-Path $packageDir "Start-F18-Radar.cmd")
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README-TEST.txt") -Destination (Join-Path $packageDir "README-TEST.txt")

    $versionInfo = @(
        "name=$packageName"
        "version=$Version"
        "built_at=$([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss zzz'))"
        "python=3.10"
        "platform=windows-x64"
    )
    Set-Content -LiteralPath (Join-Path $packageDir "version.txt") -Value $versionInfo -Encoding UTF8

    Compress-Archive -LiteralPath $packageDir -DestinationPath $zipPath -CompressionLevel Optimal
    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $checksumPath -Value "$zipHash  $packageName.zip" -Encoding ASCII
    Write-Host "Portable directory: $packageDir"
    Write-Host "Portable zip:       $zipPath"
    Write-Host "SHA-256:            $zipHash"
} finally {
    Pop-Location
}

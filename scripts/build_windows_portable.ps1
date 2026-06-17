param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildDir = Join-Path $Root "build"
$DistDir = Join-Path $Root "dist"
$ReleaseDir = Join-Path $Root "release"
$SpecPath = Join-Path $Root "packaging\RiftBGM.spec"
$AppDir = Join-Path $DistDir "RiftBGM"
$ZipPath = Join-Path $ReleaseDir "RiftBGM-v$Version-windows-x64.zip"

if (Test-Path $BuildDir) {
    Remove-Item -LiteralPath $BuildDir -Recurse -Force
}
if (Test-Path $DistDir) {
    Remove-Item -LiteralPath $DistDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Push-Location $Root
try {
    python -m PyInstaller --noconfirm --clean --distpath $DistDir --workpath $BuildDir $SpecPath
}
finally {
    Pop-Location
}

if (-not (Test-Path (Join-Path $AppDir "RiftBGM.exe"))) {
    throw "Build failed: RiftBGM.exe was not created."
}

Compress-Archive -Path $AppDir -DestinationPath $ZipPath -Force

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    $forbiddenPatterns = @(
        "(^|/)data/bilibili_",
        "(^|/)data/app_state\.json$",
        "(^|/)data/bgm_authorized_manifest\.json$",
        "(^|/)assets/champions/",
        "(^|/)docs/",
        "(^|/)utils/",
        "__pycache__",
        "\.pyc$",
        "\.log$",
        "easyocr",
        "torch",
        "torchvision",
        "(^|/)cv2(/|$)",
        "(^|/)numpy(/|$)",
        "QtWebEngine"
    )
    $badEntries = @()
    foreach ($entry in $archive.Entries) {
        $name = $entry.FullName.Replace("\", "/")
        foreach ($pattern in $forbiddenPatterns) {
            if ($name -match $pattern) {
                $badEntries += $entry.FullName
                break
            }
        }
    }
    if ($badEntries.Count -gt 0) {
        $preview = ($badEntries | Select-Object -First 30) -join "`n"
        throw "Release archive contains forbidden files:`n$preview"
    }
}
finally {
    $archive.Dispose()
}

$sizeMb = [Math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
if (Test-Path $BuildDir) {
    Remove-Item -LiteralPath $BuildDir -Recurse -Force
}
Write-Host "Built $ZipPath ($sizeMb MB)"

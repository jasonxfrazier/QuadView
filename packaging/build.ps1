param([string]$Compiler = '')
$ErrorActionPreference = 'Stop'
$rootDirectory = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $rootDirectory
uv sync --group build --locked
if ($LASTEXITCODE) { throw 'uv sync failed' }
New-Item -ItemType Directory -Path build -Force | Out-Null
uv run --no-sync python packaging/prepare.py
if ($LASTEXITCODE) { throw 'Build preparation failed' }
$env:QUADVIEW_BROWSER_BUNDLE = Join-Path $rootDirectory 'build\ms-playwright'
uv run --no-sync pyinstaller --noconfirm --clean packaging/quadview.spec
if ($LASTEXITCODE) { throw 'PyInstaller failed' }
if (-not $Compiler) {
    $localCompiler = Join-Path $rootDirectory 'build\tools\Inno Setup\ISCC.exe'
    if (Test-Path -LiteralPath $localCompiler) { $Compiler = $localCompiler }
    else { $Compiler = (Get-Command ISCC.exe -ErrorAction Stop).Source }
}
$version = uv run --no-sync python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"
& $Compiler "/DAppVersion=$version" packaging/quadview.iss
if ($LASTEXITCODE) { throw 'Installer compilation failed' }
$installerHash = Get-FileHash -Algorithm SHA256 -LiteralPath "dist\QuadViewSetup-$version.exe"
($installerHash.Hash.ToLower() + "  QuadViewSetup-$version.exe") |
    Set-Content -LiteralPath "dist\QuadViewSetup-$version.sha256" -Encoding ascii
Copy-Item -LiteralPath packaging\README.txt -Destination dist\README.txt
$installerHash

param(
    [switch]$PortableOnly
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$iss = Join-Path $root "LuminaStudio.iss"
$icon = Join-Path $root "assets\lumina.ico"
$locales = Join-Path $root "locales"
$lockFile = Join-Path $root "requirements-lock.txt"

if (-not (Test-Path $python)) {
    throw "Ambiente Python não encontrado. Crie .venv e instale requirements.txt antes de compilar."
}
if (-not (Test-Path $icon)) {
    throw "Ícone do aplicativo não encontrado: $icon"
}
foreach ($language in @("pt_BR", "en", "es")) {
    if (-not (Test-Path (Join-Path $locales "$language.json"))) {
        throw "Arquivo de tradução ausente: $(Join-Path $locales "$language.json")"
    }
}
if (-not (Test-Path $lockFile)) {
    throw "Arquivo de dependências fixadas não encontrado: $lockFile"
}

$pythonInfoJson = & $python -I -c "import json,platform,struct,sys; print(json.dumps({'version': platform.python_version(), 'major': sys.version_info.major, 'minor': sys.version_info.minor, 'bits': struct.calcsize('P')*8, 'prefix': sys.prefix, 'base_prefix': sys.base_prefix}))"
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível consultar o ambiente Python de compilação."
}
$pythonInfo = ($pythonInfoJson -join "`n") | ConvertFrom-Json
if ($pythonInfo.major -ne 3 -or $pythonInfo.minor -ne 12 -or $pythonInfo.bits -ne 64) {
    throw "A compilação exige Python 3.12 de 64 bits; encontrado Python $($pythonInfo.version) de $($pythonInfo.bits) bits."
}
if ($pythonInfo.prefix -eq $pythonInfo.base_prefix) {
    throw "A compilação deve usar um ambiente virtual .venv isolado, não o Python global."
}
$venvConfig = Join-Path (Split-Path -Parent (Split-Path -Parent $python)) "pyvenv.cfg"
if (-not (Test-Path $venvConfig)) {
    throw "Configuração do ambiente virtual não encontrada: $venvConfig"
}
if (Select-String -Path $venvConfig -Pattern '^\s*include-system-site-packages\s*=\s*true\s*$') {
    throw "O ambiente virtual permite pacotes globais. Recrie .venv sem system-site-packages."
}

$pyinstallerVersion = & $python -I -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller não está instalado em .venv. Instale requirements-build.txt."
}
if ([version]$pyinstallerVersion -lt [version]"6.1") {
    throw "PyInstaller 6.1 ou posterior é necessário para configurar a pasta interna do runtime."
}
& $python -I -m pip check
if ($LASTEXITCODE -ne 0) {
    throw "O ambiente virtual contém dependências incompatíveis. Corrija pip check antes de compilar."
}
$lockedPackages = Get-Content $lockFile | Where-Object { $_ -and -not $_.StartsWith("#") }
$installedPackages = & $python -I -m pip freeze --local
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível verificar as versões instaladas."
}
$packageDifferences = Compare-Object `
    -ReferenceObject ($lockedPackages | Sort-Object) `
    -DifferenceObject ($installedPackages | Sort-Object) `
    -CaseSensitive
if ($packageDifferences) {
    throw "As dependências instaladas não correspondem a requirements-lock.txt. Recrie .venv e instale os arquivos documentados."
}

$sourcePythonDll = Join-Path $pythonInfo.base_prefix "python312.dll"
if (-not (Test-Path $sourcePythonDll)) {
    throw "DLL do interpretador ausente no ambiente de compilação: $sourcePythonDll"
}
$sourceDllVersion = (Get-Item $sourcePythonDll).VersionInfo.FileVersion
if ($sourceDllVersion -ne $pythonInfo.version) {
    throw "A DLL do interpretador ($sourceDllVersion) não corresponde ao Python $($pythonInfo.version)."
}

$compiler = $null
if (-not $PortableOnly) {
    $compiler = (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue).Source
    if (-not $compiler) {
        $candidates = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
        )
        $compiler = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $compiler) {
        throw "Inno Setup 6 não encontrado. Instale-o ou use -PortableOnly para validar a pasta onedir."
    }
}

Push-Location $root
try {
    & $python -I -m PyInstaller --noconfirm --onedir --noupx --windowed `
        --clean `
        --name LuminaStudio `
        --icon $icon `
        --add-data "$icon;assets" `
        --add-data "$locales;locales" `
        --contents-directory _internal `
        --specpath .\build\installer-build `
        --workpath .\build\installer-build `
        --distpath .\dist\installer-build `
        --collect-all tkinterdnd2 `
        --hidden-import basicsr.archs.rrdbnet_arch `
        --hidden-import realesrgan `
        --hidden-import gfpgan `
        --collect-all torchvision `
        --collect-all imageio_ffmpeg `
        .\main.py
    if ($LASTEXITCODE -ne 0) {
        throw "A compilação do aplicativo falhou (código $LASTEXITCODE)."
    }

    $distribution = Join-Path $root "dist\installer-build\LuminaStudio"
    & $python -I .\build_support.py $distribution
    if ($LASTEXITCODE -ne 0) {
        throw "A distribuição onedir está incompleta ou contém binários incompatíveis."
    }
    $bundledPythonDll = Join-Path $distribution "_internal\python312.dll"
    $bundledDllVersion = (Get-Item $bundledPythonDll).VersionInfo.FileVersion
    if ($bundledDllVersion -ne $pythonInfo.version) {
        throw "A DLL empacotada ($bundledDllVersion) não corresponde ao Python de build ($($pythonInfo.version))."
    }

    if (-not $PortableOnly) {
        & $compiler $iss
        if ($LASTEXITCODE -ne 0) {
            throw "A criação do instalador falhou (código $LASTEXITCODE)."
        }
    }
}
finally {
    Pop-Location
}

if ($PortableOnly) {
    Write-Host "Distribuição portátil criada e validada em dist\installer-build\LuminaStudio"
}
else {
    Write-Host "Instalador criado em dist\LuminaStudio-Setup.exe"
}

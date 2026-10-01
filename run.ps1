param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8501
)

$ErrorActionPreference = 'Stop'
$cvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$cvApp = Join-Path $PSScriptRoot 'app.py'
if (-not (Test-Path -LiteralPath $cvPython)) {
    throw 'Create .venv and install requirements.txt first. See README.md.'
}

Push-Location $PSScriptRoot
try {
    & $cvPython -m streamlit run $cvApp "--server.port=$Port" --server.headless=true
    if ($LASTEXITCODE -ne 0) {
        throw "Streamlit exited with code $LASTEXITCODE. Check that port $Port is available."
    }
}
finally {
    Pop-Location
}

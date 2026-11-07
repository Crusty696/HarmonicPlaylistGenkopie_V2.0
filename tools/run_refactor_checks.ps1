param(
    [Parameter(Mandatory = $true)][string]$Label,
    [string[]]$TestFiles = @('tests/'),
    [string]$EvidenceDirectory,
    [switch]$Full,
    [ValidateRange(1, 64)][int]$AutoWorkers
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot 'venv312\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Projektinterpreter fehlt' }
$runRoot = $EvidenceDirectory
if (-not $runRoot) { $runRoot = Join-Path $env:TEMP ('hpg-refactor-' + [guid]::NewGuid().ToString('N')) }
if (-not (Test-Path -LiteralPath $runRoot)) { New-Item -ItemType Directory -Path $runRoot | Out-Null }
$runRoot = (Resolve-Path -LiteralPath $runRoot).Path
if ($Label -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Ungültiger Nachweisname' }
$logPath = Join-Path $runRoot ($Label + '.log')
if (Test-Path -LiteralPath $logPath) { throw 'Vorhandener Nachweis wird nicht überschrieben' }
$coveragePath = Join-Path $runRoot ($Label + '.coverage')
if (Test-Path -LiteralPath $coveragePath) { throw 'Vorhandene Coverage wird nicht überschrieben' }
$env:QT_QPA_PLATFORM = 'offscreen'
$env:COVERAGE_FILE = $coveragePath
if ($PSBoundParameters.ContainsKey('AutoWorkers')) { $env:PYTEST_XDIST_AUTO_NUM_WORKERS = [string]$AutoWorkers }
$pytestArgs = @('-m', 'pytest') + $TestFiles + @('--tb=short', '-q')
if (-not $Full) { $pytestArgs += @('--no-cov', '-n', '0') }
$sourceFiles = @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'hpg_core'), (Join-Path $projectRoot 'tests'), (Join-Path $projectRoot 'tools') -Recurse -File -Filter '*.py')
$sourceFiles += Get-Item -LiteralPath (Join-Path $projectRoot 'main.py'), (Join-Path $projectRoot 'pytest.ini')
$sourceFiles += Get-Item -LiteralPath $PSCommandPath
$hashes = @{}
foreach ($sourceFile in $sourceFiles) {
    $relativePath = $sourceFile.FullName.Substring($projectRoot.Length + 1)
    $hashes[$relativePath] = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash
}
$manifest = @{
    startedUtc = [DateTime]::UtcNow.ToString('o')
    interpreter = $python
    pythonVersion = (& $python --version)
    arguments = $pytestArgs
    sourceSha256 = $hashes
    coverageFile = $env:COVERAGE_FILE
    qtPlatform = $env:QT_QPA_PLATFORM
    pytestAutoWorkers = $env:PYTEST_XDIST_AUTO_NUM_WORKERS
}
$manifestPath = Join-Path $runRoot ($Label + '.json')
if (Test-Path -LiteralPath $manifestPath) { throw 'Vorhandenes Manifest wird nicht überschrieben' }
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding utf8
& $python @pytestArgs *> $logPath
$testExit = $LASTEXITCODE
$manifest['exitCode'] = $testExit
$manifest['finishedUtc'] = [DateTime]::UtcNow.ToString('o')
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Get-Content -LiteralPath $logPath -Tail 18
Write-Output ('Nachweis: ' + $logPath)
exit $testExit

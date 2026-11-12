param(
    [Parameter(Mandatory = $true)][string]$ProbeScript
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot 'venv312\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $availablePython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $availablePython) {
        $availablePython = Get-Command python -ErrorAction SilentlyContinue
    }
    if ($null -ne $availablePython) {
        $python = $availablePython.Source
    }
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
    -not (Test-Path -LiteralPath $ProbeScript -PathType Leaf)) {
    throw 'Probe oder Projektinterpreter fehlt'
}
$resolvedProbe = (Resolve-Path -LiteralPath $ProbeScript).Path
if ([IO.Path]::GetExtension($resolvedProbe) -ne '.py' -or $resolvedProbe -match '["\r\n]') {
    throw 'Probe muss eine Python-Datei mit gueltigem Pfad sein'
}
# Jeder Start erhält eigene Logs; historische Nachweise bleiben erhalten.
# Den Zustand innerhalb der Probe muss deren Aufrufer ebenfalls isolieren.
$logRoot = Join-Path $env:TEMP ('hpg-probe-launch-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $logRoot -ErrorAction Stop | Out-Null
$process = Start-Process -FilePath $python -ArgumentList @('"' + $resolvedProbe + '"') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot 'stdout.log') -RedirectStandardError (Join-Path $logRoot 'stderr.log')
Write-Output ('Eigene App-PID: ' + $process.Id)
Write-Output ('Startprotokolle: ' + $logRoot)

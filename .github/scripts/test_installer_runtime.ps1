[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,

    [Parameter(Mandatory = $true)]
    [string]$StandaloneExePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$installer = (Resolve-Path -LiteralPath $InstallerPath).Path
$standaloneExe = (Resolve-Path -LiteralPath $StandaloneExePath).Path
$runnerTemp = if ($env:RUNNER_TEMP) {
    (Resolve-Path -LiteralPath $env:RUNNER_TEMP).Path
} else {
    [System.IO.Path]::GetTempPath()
}
$smokeRoot = Join-Path $runnerTemp ("HPG-Installer-Smoke-" + [guid]::NewGuid().ToString("N"))
$installDir = Join-Path $smokeRoot "app"
$installedExe = Join-Path $installDir "HarmonicPlaylistGenerator.exe"
$uninstaller = Join-Path $installDir "unins000.exe"
$cacheFile = Join-Path $smokeRoot "hpg_installer_smoke_cache.db"
$audioA = Join-Path $smokeRoot "hpg_worker_smoke_a.wav"
$audioB = Join-Path $smokeRoot "hpg_worker_smoke_b.wav"
$previousCacheFile = [Environment]::GetEnvironmentVariable("HPG_CACHE_FILE", "Process")
$workerSmoke = $null
$app = $null
$installCompleted = $false
$failure = $null
$cleanupErrors = [System.Collections.Generic.List[string]]::new()

New-Item -ItemType Directory -Path $smokeRoot | Out-Null

try {
    $install = Start-Process -FilePath $installer -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/DIR=`"$installDir`""
    ) -PassThru
    if (-not $install.WaitForExit(120000)) {
        Stop-Process -Id $install.Id -Force -ErrorAction SilentlyContinue
        throw "Installer timed out"
    }
    if ($install.ExitCode -ne 0) {
        throw "Installer failed with $($install.ExitCode)"
    }
    $installCompleted = $true
    if (-not (Test-Path -LiteralPath $installedExe -PathType Leaf)) {
        throw "Installed executable missing"
    }

    $installedHash = (Get-FileHash -LiteralPath $installedExe -Algorithm SHA256).Hash
    $standaloneHash = (Get-FileHash -LiteralPath $standaloneExe -Algorithm SHA256).Hash
    if ($installedHash -ne $standaloneHash) {
        throw "Installed executable differs from standalone release executable"
    }

    $env:HPG_CACHE_FILE = $cacheFile
    @'
import sys
import numpy as np
import soundfile as sf

sr = 22050
seconds = 20.0
samples = np.arange(int(sr * seconds), dtype=np.float64)
for index, path in enumerate(sys.argv[1:]):
    audio = 0.08 * np.sin(2.0 * np.pi * (110.0 + index * 55.0) * samples / sr)
    kernel = np.exp(-np.arange(int(sr * 0.04), dtype=np.float64) / (sr * 0.008))
    interval = int(sr * 60.0 / (138.0 + index * 2.0))
    for start in range(0, samples.size, interval):
        end = min(start + kernel.size, samples.size)
        audio[start:end] += 0.8 * kernel[:end - start]
    sf.write(path, np.clip(audio, -1.0, 1.0).astype(np.float32), sr)
'@ | python - $audioA $audioB
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to generate isolated worker-smoke audio"
    }

    $workerInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $workerInfo.FileName = $installedExe
    $workerInfo.UseShellExecute = $false
    $workerInfo.CreateNoWindow = $true
    $workerLocalAppData = Join-Path $smokeRoot "worker-localappdata"
    $workerInfo.Environment["LOCALAPPDATA"] = $workerLocalAppData
    [void]$workerInfo.ArgumentList.Add("--worker-smoke")
    [void]$workerInfo.ArgumentList.Add($audioA)
    [void]$workerInfo.ArgumentList.Add($audioB)
    $workerSmoke = [System.Diagnostics.Process]::Start($workerInfo)
    if (-not $workerSmoke.WaitForExit(180000)) {
        throw "Frozen worker smoke timed out"
    }
    if ($workerSmoke.ExitCode -ne 0) {
        $workerLogPath = Join-Path $workerLocalAppData "HPG\logs\hpg.log"
        $workerLogTail = if (Test-Path -LiteralPath $workerLogPath -PathType Leaf) {
            (Get-Content -LiteralPath $workerLogPath -Tail 60) -join [Environment]::NewLine
        } else {
            "Worker log was not created at $workerLogPath"
        }
        throw "Frozen worker smoke failed with $($workerSmoke.ExitCode):`n$workerLogTail"
    }
    if (-not (Test-Path -LiteralPath $cacheFile -PathType Leaf)) {
        throw "Frozen worker smoke did not create its isolated cache"
    }
    $cacheQuery = @'
import json
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
track_rows = conn.execute(
    "SELECT COUNT(*) FROM cache WHERE key <> ?", ("version",)
).fetchone()[0]
version_markers = conn.execute(
    "SELECT COUNT(*) FROM cache WHERE key = ?", ("version",)
).fetchone()[0]
print(json.dumps({"track_rows": track_rows, "version_markers": version_markers}))
'@
    $cacheStateJson = $cacheQuery | python - $cacheFile
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect the isolated worker-smoke cache"
    }
    $cacheState = $cacheStateJson | ConvertFrom-Json
    if ([int]$cacheState.version_markers -ne 1) {
        throw "Frozen worker smoke cache did not keep exactly one version marker"
    }
    # Native phrase analysis is intentionally non-cacheable when its model is
    # unavailable; unit contracts cover persistence for cacheable analyses.
    Write-Host "Frozen worker smoke cache track rows: $($cacheState.track_rows)"

    $app = Start-Process -FilePath $installedExe -WindowStyle Hidden -PassThru
    $guiDeadline = [System.Diagnostics.Stopwatch]::StartNew()
    $mainWindowReady = $false
    while ($guiDeadline.Elapsed.TotalSeconds -lt 30) {
        if ($app.HasExited) {
            throw "Installed application exited with $($app.ExitCode)"
        }
        $app.Refresh()
        if ($app.MainWindowHandle -ne [IntPtr]::Zero -and
            -not [string]::IsNullOrWhiteSpace($app.MainWindowTitle)) {
            $mainWindowReady = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $mainWindowReady) {
        throw "Installed application did not create a main window with a title"
    }
} catch {
    $failure = $_
} finally {
    foreach ($entry in @(
        @{ Process = $workerSmoke; Name = "worker smoke" },
        @{ Process = $app; Name = "GUI smoke" }
    )) {
        $process = $entry.Process
        if ($null -eq $process) {
            continue
        }
        try {
            if (-not $process.HasExited) {
                & taskkill.exe /PID $process.Id /T /F | Out-Host
                [void]$process.WaitForExit(10000)
            }
            if (-not $process.HasExited) {
                $cleanupErrors.Add("$($entry.Name) process tree did not stop")
            }
        } catch {
            $cleanupErrors.Add("$($entry.Name) cleanup failed: $($_.Exception.Message)")
        }
    }

    if (Test-Path -LiteralPath $uninstaller -PathType Leaf) {
        try {
            $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @(
                "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
            ) -PassThru
            if (-not $uninstall.WaitForExit(120000)) {
                Stop-Process -Id $uninstall.Id -Force -ErrorAction SilentlyContinue
                $cleanupErrors.Add("Uninstaller timed out")
            } elseif ($uninstall.ExitCode -ne 0) {
                $cleanupErrors.Add("Uninstaller failed with $($uninstall.ExitCode)")
            }
        } catch {
            $cleanupErrors.Add("Uninstaller cleanup failed: $($_.Exception.Message)")
        }
    } elseif ($installCompleted) {
        $cleanupErrors.Add("Uninstaller missing after successful installation")
    }

    Start-Sleep -Seconds 2
    if ($installCompleted -and (Test-Path -LiteralPath $installedExe)) {
        $cleanupErrors.Add("Uninstall left the application executable behind")
    }

    if ($null -eq $previousCacheFile) {
        Remove-Item Env:HPG_CACHE_FILE -ErrorAction SilentlyContinue
    } else {
        $env:HPG_CACHE_FILE = $previousCacheFile
    }

    try {
        if (Test-Path -LiteralPath $smokeRoot) {
            Remove-Item -LiteralPath $smokeRoot -Recurse -Force
        }
    } catch {
        $cleanupErrors.Add("Runner-temp cleanup failed: $($_.Exception.Message)")
    }
}

if ($null -ne $failure) {
    if ($cleanupErrors.Count -ne 0) {
        throw "$($failure.Exception.Message); cleanup: $($cleanupErrors -join '; ')"
    }
    throw $failure
}
if ($cleanupErrors.Count -ne 0) {
    throw ($cleanupErrors -join "; ")
}

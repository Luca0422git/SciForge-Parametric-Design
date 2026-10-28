# SciForge: checks that the Windows installer never leaves a half-deleted SciForge
# (docs/sciforge/core-patches.md #19). Run on a Windows runner by the patch release and the
# full build after the installer is made; it can also be run by hand, as an administrator:
#   powershell -ExecutionPolicy Bypass -File tools\sciforge\test_installer.ps1 -Installer <exe>
#
# The bug (Luca, 2026-10-28): updating to a new full build, the installer deleted every file of
# C:\Program Files\SciForge it could, stopped at the files SciForge's AI connector had open (its
# own bin\python.exe, kept running by Claude Desktop), said "Failed to remove" and quit: no
# SciForge left. Checked here, silently (/S answers every question with its default):
#   A  installing over a SciForge whose AI connector runs: the connector is stopped, the new
#      SciForge is complete, the old folder is gone (no "<folder>.old" left);
#   B  installing while a file in the folder is held open by another program: the installer
#      either stops with the old SciForge untouched, or (when Windows lets the folder move
#      anyway) installs a complete new one; never half of either;
#   C  uninstalling while the connector runs: the connector is stopped, the program is gone.
param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [string]$Dir = "C:\sftest\SciForge"  # (no spaces: NSIS takes /D= unquoted)
)
$ErrorActionPreference = "Stop"
$failures = @()

function Check($ok, $what) {
    if ($ok) { Write-Host "ok   $what" } else { Write-Host "FAIL $what"; $script:failures += $what }
}

function Run-Installer {
    $p = Start-Process -FilePath $Installer -ArgumentList "/S", "/D=$Dir" -Wait -PassThru
    return $p.ExitCode
}

# The installer refuses to install the same version over itself ("already installed", which
# /S answers with Cancel). An update installs another version: the uninstall entry's
# UninstallString is taken away so this one installs over the folder as an update does.
function Forget-Installed {
    Get-ChildItem "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
        Where-Object { $_.PSChildName -like "SciForge*" } |
        ForEach-Object { Remove-ItemProperty -Path $_.PSPath -Name UninstallString -ErrorAction SilentlyContinue }
}

function Complete {
    return (Test-Path "$Dir\bin\SciForge.exe") -and (Test-Path "$Dir\bin\python.exe") -and
        (Test-Path "$Dir\Mod\SciForge\VERSION") -and (Test-Path "$Dir\Uninstall-SciForge.exe")
}

function File-Count { return @(Get-ChildItem -LiteralPath $Dir -Recurse -File -Force).Count }

# SciForge's AI connector as Claude Desktop runs it: the bundled python.exe, kept running.
function Start-Connector {
    $p = Start-Process -FilePath "$Dir\bin\python.exe" -ArgumentList "-c", "`"import time; time.sleep(900)`"" `
        -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 3
    return $p
}

function Leftovers { return @(Get-ChildItem -Path (Split-Path -Parent $Dir) -Directory -Filter "SciForge.old*" -ErrorAction SilentlyContinue) }

try {
    if (Test-Path $Dir) { Remove-Item -LiteralPath $Dir -Recurse -Force }
    Write-Host "[SciForge] installer: $Installer"
    Write-Host "[SciForge] folder: $Dir"

    $code = Run-Installer
    Check ($code -eq 0 -and (Complete)) "a first install into $Dir (exit $code)"
    if (-not (Complete)) { throw "the first install did not work: nothing else can be checked" }
    $files = File-Count

    # -- A: over a running AI connector
    Forget-Installed
    $marker = "$Dir\old-version-marker.txt"
    Set-Content -LiteralPath $marker -Value "the old version"
    $connector = Start-Connector
    Check (-not $connector.HasExited) "A: the connector stand-in runs ($Dir\bin\python.exe)"
    $code = Run-Installer
    $connector.Refresh()
    Check ($code -eq 0) "A: the installer finished (exit $code)"
    Check ($connector.HasExited) "A: the AI connector was stopped"
    Check (Complete) "A: the new SciForge is complete"
    Check (-not (Test-Path $marker)) "A: the old folder was replaced (its marker file is gone)"
    Check ((File-Count) -ge $files) "A: every file is there ($(File-Count) of $files)"
    Check ((Leftovers).Count -eq 0) "A: no old folder left ($((Leftovers) -join ', '))"
    if (-not $connector.HasExited) { Stop-Process -Id $connector.Id -Force -ErrorAction SilentlyContinue }

    # -- B: a file in the folder held open by another program
    Forget-Installed
    Set-Content -LiteralPath $marker -Value "the old version"
    $files = File-Count
    $held = [IO.File]::Open("$Dir\Mod\SciForge\VERSION", [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
    try {
        $code = Run-Installer
    } finally {
        $held.Close()
    }
    if (Test-Path $marker) {
        Check ($code -ne 0) "B: the installer stopped (exit $code)"
        Check ((Complete) -and (File-Count) -eq $files) "B: the old SciForge is untouched ($(File-Count) of $files files)"
        Write-Host "     (B: Windows did not let the folder move while a file in it was open: nothing changed)"
    } else {
        Check ($code -eq 0) "B: the installer finished (exit $code)"
        Check (Complete) "B: the new SciForge is complete"
        Write-Host "     (B: Windows let the folder move; the old copy's open file stays in the .old folder)"
    }
    foreach ($left in Leftovers) { Remove-Item -LiteralPath $left.FullName -Recurse -Force -ErrorAction SilentlyContinue }

    # -- C: uninstall while the connector runs
    if (-not (Complete)) { throw "no complete SciForge to uninstall" }
    $connector = Start-Connector
    $p = Start-Process -FilePath "$Dir\Uninstall-SciForge.exe" -ArgumentList "/S", "_?=$Dir" -Wait -PassThru
    $connector.Refresh()
    Check ($p.ExitCode -eq 0) "C: the uninstaller finished (exit $($p.ExitCode))"
    Check ($connector.HasExited) "C: the AI connector was stopped"
    Check (-not (Test-Path "$Dir\bin")) "C: the program is gone"
    if (-not $connector.HasExited) { Stop-Process -Id $connector.Id -Force -ErrorAction SilentlyContinue }
} catch {
    Check $false "the test itself: $($_.Exception.Message)"
} finally {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith("$Dir\", [StringComparison]::OrdinalIgnoreCase) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath (Split-Path -Parent $Dir) -Recurse -Force -ErrorAction SilentlyContinue
}

if ($failures.Count -gt 0) {
    Write-Host "[SciForge] installer test: $($failures.Count) check(s) failed"
    exit 1
}
Write-Host "[SciForge] installer test: all checks passed"
exit 0

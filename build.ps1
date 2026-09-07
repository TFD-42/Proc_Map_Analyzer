<#
build.ps1 - reproducible PyInstaller build of process_analyzer_allinone.py
on Windows (macOS/Linux use build.sh).

Steps (each printed as it runs, nothing hidden):
  1. Dedicated build venv  .venv-build\  (separate from the runtime .venv)
  2. Pinned dependencies: requirements_frozen.txt (runtime, exact versions)
     + requirements_build.txt (pyinstaller, exact version)
  3. Compile check (compile_check.py, in memory)
  4. pyinstaller --onefile --console --collect-all psutil
     --collect-submodules matplotlib   (flag set documented in the README;
     --collect-all psutil is mandatory)
  5. Smoke test: the freshly built .exe runs a real short analysis
     (--no-enrich, 5 processes, HTML only) and the HTML must be non-empty
  6. SHA-256 of the artifact written next to it (dist\ProcessAnalyzer.exe.sha256)

Usage:
  powershell -ExecutionPolicy Bypass -File build.ps1
  powershell -ExecutionPolicy Bypass -File build.ps1 -SkipSmoke

Output: dist\ProcessAnalyzer.exe (+ .sha256). Work files in build\ (safe to
delete). Both dirs are git-ignored. PyInstaller does not cross-compile: run
this ON Windows to get a Windows executable.

NOTE: this script mirrors build.sh step by step but was written on macOS
without a Windows machine to run it on - it has been syntax-reviewed, not
executed. If it fails for you, the failing step is printed; please open an
issue with that output.
#>
param(
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyScript  = Join-Path $ScriptDir "process_analyzer_allinone.py"
$BuildVenv = Join-Path $ScriptDir ".venv-build"
$ReqFrozen = Join-Path $ScriptDir "requirements_frozen.txt"
$ReqBuild  = Join-Path $ScriptDir "requirements_build.txt"
$Checker   = Join-Path $ScriptDir "compile_check.py"
$DistDir   = Join-Path $ScriptDir "dist"
$WorkDir   = Join-Path $ScriptDir "build"
$AppName   = "ProcessAnalyzer"

function Log($msg)  { Write-Host "`n[build] $msg" -ForegroundColor Cyan }
function Err($msg)  { Write-Host "[error] $msg" -ForegroundColor Red }

foreach ($f in @($PyScript, $ReqFrozen, $ReqBuild, $Checker)) {
    if (-not (Test-Path $f)) { Err "Missing file: $f"; exit 1 }
}

# 1. Python + build venv ------------------------------------------------------
$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        $verOut = & $candidate --version 2>&1
        if ($verOut -match "Python 3") { $pythonCmd = $candidate; break }
    }
}
if (-not $pythonCmd) { Err "Python 3 not found. Run install.ps1 first (it installs Python)."; exit 1 }
Log "Python: $(& $pythonCmd --version 2>&1)"

$VPy = Join-Path $BuildVenv "Scripts\python.exe"
if (-not (Test-Path $VPy)) {
    Log "Creating build venv: $BuildVenv"
    & $pythonCmd -m venv $BuildVenv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VPy)) { Err "venv creation failed."; exit 1 }
} else {
    Log "Reusing build venv: $BuildVenv"
}

# 2. Pinned dependencies -------------------------------------------------------
Log "Installing pinned dependencies:  pip install -r requirements_frozen.txt -r requirements_build.txt"
& $VPy -m pip install --upgrade pip --quiet
& $VPy -m pip install --quiet -r $ReqFrozen -r $ReqBuild
if ($LASTEXITCODE -ne 0) { Err "pip install failed (see above)."; exit 1 }
Log "PyInstaller: $(& $VPy -m PyInstaller --version 2>$null)"

# 3. Compile check -------------------------------------------------------------
Log "Compile check"
& $VPy $Checker
if ($LASTEXITCODE -ne 0) { Err "Compile check failed - not building."; exit 1 }

# 4. Build ---------------------------------------------------------------------
Log "Running PyInstaller (this takes a minute or two)"
if (Test-Path $WorkDir) { Remove-Item -Recurse -Force $WorkDir }
$Exe = Join-Path $DistDir "$AppName.exe"
if (Test-Path $Exe) { Remove-Item -Force $Exe }
if (Test-Path "$Exe.sha256") { Remove-Item -Force "$Exe.sha256" }
$piArgs = @("-m", "PyInstaller", "--clean", "--noconfirm", "--onefile", "--console", "--name", $AppName,
            "--collect-all", "psutil", "--collect-submodules", "matplotlib",
            "--distpath", $DistDir, "--workpath", $WorkDir, "--specpath", $WorkDir, $PyScript)
Write-Host "+ $VPy $($piArgs -join ' ')"
& $VPy @piArgs
if ($LASTEXITCODE -ne 0) { Err "PyInstaller failed (exit $LASTEXITCODE)."; exit $LASTEXITCODE }
if (-not (Test-Path $Exe)) { Err "Build finished but $Exe is missing."; exit 1 }
Log "Built: $Exe ($([math]::Round((Get-Item $Exe).Length / 1MB, 1)) MB)"

# 5. Smoke test ----------------------------------------------------------------
if ($SkipSmoke) {
    Log "Smoke test skipped (-SkipSmoke)."
} else {
    $SmokeHtml = Join-Path $env:TEMP "pma_build_smoke.$PID.html"
    Log "Smoke test:  $Exe --no-enrich --max-processes 5 --html-output $SmokeHtml"
    # An empty line is piped to stdin on purpose: a frozen executable pauses on
    # "Press Enter to close this window..." before exiting, which would hang an
    # unattended build forever.
    "" | & $Exe --no-enrich --max-processes 5 --html-output $SmokeHtml | Out-Null
    if ($LASTEXITCODE -eq 0 -and (Test-Path $SmokeHtml) -and (Get-Item $SmokeHtml).Length -gt 0) {
        Log "Smoke test OK (HTML produced: $([math]::Round((Get-Item $SmokeHtml).Length / 1KB)) KB)"
        Remove-Item -Force $SmokeHtml
    } else {
        Err "Smoke test FAILED: the executable did not produce a non-empty HTML. Re-run it by hand to see its output:"
        Err "  $Exe --no-enrich --max-processes 5 --html-output $SmokeHtml"
        exit 1
    }
}

# 6. Checksum ------------------------------------------------------------------
$hash = (Get-FileHash -Algorithm SHA256 $Exe).Hash.ToLower()
"$hash  $AppName.exe" | Set-Content -Path "$Exe.sha256" -Encoding ASCII
Log "SHA-256: $hash  (written to dist\$AppName.exe.sha256)"
Log "Done. Executable: $Exe"

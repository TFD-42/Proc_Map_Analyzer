<#
.SYNOPSIS
    Automatically installs everything needed to run
    process_analyzer_allinone.py on a clean Windows machine, then
    launches the script.

.DESCRIPTION
    Order of steps (each one first checks whether it's already present, and
    never reinstalls anything unnecessarily):
      1. Ollama (local AI engine) - via winget if available, otherwise
         direct download of the official installer.
      2. An Ollama model suited to the machine: MEDIUM (llama3:latest,
         ~4.7 GB) on Windows — the MINI variant (llama3.2:1b) is reserved
         for Android/Termux, handled by install.sh (same selection policy).
      3. Python 3 - via winget if available, otherwise direct download.
      4. Creation + activation of a virtual environment (.venv).
      5. Python dependencies (pip).
      6. Launching process_analyzer_allinone.py.

.NOTES
    If script execution is blocked by Windows' default policy, run this
    script with:
        powershell -ExecutionPolicy Bypass -File install.ps1

    Arguments passed to this script are forwarded as-is to the Python
    script (e.g.: .\install.ps1 --no-enrich --max-processes 50).
#>

param(
    # -InstallOnly : install + compile check, do NOT launch the analyzer.
    [switch]$InstallOnly,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PyArgs
)

# PMA_SKIP_OLLAMA=1 (environment variable, same name as in install.sh):
# skip steps 1-2 entirely — no Ollama install, no server start, no model
# download. Nothing is fetched from the internet except pip packages.
$SkipOllama = ($env:PMA_SKIP_OLLAMA -eq "1")

$ErrorActionPreference = "Continue"

$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyScript     = Join-Path $ScriptDir "process_analyzer_allinone.py"
$VenvDir      = Join-Path $ScriptDir ".venv"
# MEDIUM model (~4.7 GB) — per-machine policy: mini (llama3.2:1b) on
# Android/Termux via install.sh, medium on macOS/Windows/Linux.
$DefaultModel = "llama3:latest"
$OllamaHost   = "http://localhost:11434"

function Log  ($msg) { Write-Host "`n[install] $msg" -ForegroundColor Cyan }
function Warn ($msg) { Write-Host "[warning] $msg" -ForegroundColor Yellow }
function Err  ($msg) { Write-Host "[error] $msg" -ForegroundColor Red }

function Update-SessionPath {
    # Installers (winget, .exe) modify the machine/user PATH, never the
    # current PowerShell process' PATH: we reload it so freshly installed
    # binaries can be found without reopening a new window.
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

if (-not (Test-Path $PyScript)) {
    Err "process_analyzer_allinone.py not found next to this script ($ScriptDir)."
    Err "Place install.ps1 in the same folder as process_analyzer_allinone.py and rerun."
    exit 1
}

# ---------------------------------------------------------------------------
# 1. Ollama
# ---------------------------------------------------------------------------
Log "Step 1/7: checking Ollama..."
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($SkipOllama) {
    Log "PMA_SKIP_OLLAMA=1 - Ollama install/start/model download skipped (analysis will run without AI)."
} elseif ($ollamaCmd) {
    Log "Ollama already installed ($($ollamaCmd.Source))."
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Log "Installing Ollama via winget..."
        winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Warn "winget failed for Ollama - the analysis will continue without AI." }
    } else {
        Log "winget unavailable - downloading the Ollama installer directly..."
        $installer = Join-Path $env:TEMP "OllamaSetup.exe"
        try {
            Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $installer -UseBasicParsing
            Start-Process -FilePath $installer -ArgumentList "/silent" -Wait
        } catch {
            Warn "Automatic Ollama download/installation failed: $_ - the analysis will continue without AI."
        }
    }
    Update-SessionPath
}

$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd -and -not $SkipOllama) {
    $reachable = $false
    try {
        Invoke-WebRequest -Uri "$OllamaHost/api/tags" -UseBasicParsing -TimeoutSec 2 | Out-Null
        $reachable = $true
    } catch { }
    if (-not $reachable) {
        Log "Starting the Ollama server in the background..."
        Start-Process -FilePath $ollamaCmd.Source -ArgumentList "serve" -WindowStyle Hidden
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 2
            try {
                Invoke-WebRequest -Uri "$OllamaHost/api/tags" -UseBasicParsing -TimeoutSec 2 | Out-Null
                $reachable = $true
                break
            } catch { }
        }
    }
    if (-not $reachable) { Warn "The Ollama server is not responding yet - the Python script's assistant will offer to retry." }
} elseif (-not $SkipOllama) {
    Warn "Ollama could not be installed automatically - AI enrichment will be disabled (rule-based risk engine still active). Install it manually from https://ollama.com/download if needed."
}

# ---------------------------------------------------------------------------
# 2. Default Ollama model
# ---------------------------------------------------------------------------
Log "Step 2/7: checking the Ollama model ($DefaultModel)..."
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd -and -not $SkipOllama) {
    $modelBase = $DefaultModel.Split(":")[0]
    $models = & ollama list 2>$null
    if ($models -match [regex]::Escape($modelBase)) {
        Log "Model already present."
    } else {
        Log "Downloading model $DefaultModel (several GB, may take a while depending on your connection)..."
        & ollama pull $DefaultModel
        if ($LASTEXITCODE -ne 0) { Warn "Model download failed - the analysis will continue without AI (retry later: ollama pull $DefaultModel)." }
    }
} else {
    Log "Step skipped (PMA_SKIP_OLLAMA=1 or Ollama unavailable)."
}

# ---------------------------------------------------------------------------
# 3. Python 3
# ---------------------------------------------------------------------------
Log "Step 3/7: checking Python 3..."
$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        $verOut = & $candidate --version 2>&1
        if ($verOut -match "Python 3") { $pythonCmd = $candidate; break }
    }
}

if (-not $pythonCmd) {
    Log "Python 3 not found - installing..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Err "winget failed for Python."; exit 1 }
    } else {
        Log "winget unavailable - downloading the Python installer directly..."
        $installer = Join-Path $env:TEMP "python-installer.exe"
        try {
            Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe" -OutFile $installer -UseBasicParsing
            Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1" -Wait
        } catch {
            Err "Automatic Python download/installation failed: $_"
            Err "Install it manually from https://www.python.org/downloads/ then rerun this script."
            exit 1
        }
    }
    Update-SessionPath
    foreach ($candidate in @("python", "python3", "py")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) { $pythonCmd = $candidate; break }
    }
}

if (-not $pythonCmd) {
    Err "Python 3 still not found even after attempting automatic installation. Install it manually from https://www.python.org/downloads/ (check 'Add python.exe to PATH') then rerun this script."
    exit 1
}
Log "Python detected: $(& $pythonCmd --version 2>&1)"

$pyMinor = [int](& $pythonCmd -c "import sys; print(sys.version_info[1])" 2>$null)
if ($pyMinor -lt 10) {
    Err "Python 3.10+ is required since v0.3.0 (found $(& $pythonCmd --version 2>&1)): the pinned security fixes for Pillow/requests/urllib3 in requirements_frozen.txt dropped Python 3.9 support upstream."
    Err "Install a newer Python from https://www.python.org/downloads/ (check 'Add python.exe to PATH') then rerun this script."
    exit 1
}

# ---------------------------------------------------------------------------
# 4. Virtual environment + activation
# ---------------------------------------------------------------------------
Log "Step 4/7: creating the virtual environment (.venv)..."
if (-not (Test-Path $VenvDir)) {
    & $pythonCmd -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Err "Failed to create the venv."
        exit 1
    }
}

$activate = Join-Path $VenvDir "Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Err "Activation script not found ($activate)."
    exit 1
}
. $activate
Log "Venv active: $((Get-Command python).Source)"

# ---------------------------------------------------------------------------
# 5. Python dependencies
# ---------------------------------------------------------------------------
Log "Step 5/7: installing Python dependencies..."
python -m pip install --upgrade pip --quiet

# Reproducible by default: exact pinned versions from requirements_frozen.txt.
# requirements.txt (lower bounds only) is a fallback, never the first choice.
$ReqFrozen = Join-Path $ScriptDir "requirements_frozen.txt"
$ReqLoose  = Join-Path $ScriptDir "requirements.txt"
if (Test-Path $ReqFrozen) {
    $ReqFile = $ReqFrozen
    Log "Using pinned versions from requirements_frozen.txt (reproducible install)."
} elseif (Test-Path $ReqLoose) {
    $ReqFile = $ReqLoose
    Warn "requirements_frozen.txt not found - falling back to requirements.txt (lower bounds only, versions NOT pinned)."
} else {
    Err "Neither requirements_frozen.txt nor requirements.txt found next to install.ps1. Aborting."
    exit 1
}
Log "Running: python -m pip install -r $ReqFile"
python -m pip install --quiet -r $ReqFile
if ($LASTEXITCODE -ne 0) {
    Warn "Standard pip failed - retrying with --break-system-packages..."
    python -m pip install --quiet --break-system-packages -r $ReqFile
    if ($LASTEXITCODE -ne 0) {
        Err "Failed to install Python dependencies (see pip output above)."
        exit 1
    }
}
Log "Dependencies installed."

# ---------------------------------------------------------------------------
# 6. Compile check (in memory - writes NO .pyc / __pycache__)
# ---------------------------------------------------------------------------
Log "Step 6/7: compile check of the main script and plugins\ ..."
python (Join-Path $ScriptDir "compile_check.py")
if ($LASTEXITCODE -ne 0) {
    Err "Compile check failed - the code as shipped has a syntax error (see above). Not launching."
    exit 1
}

# ---------------------------------------------------------------------------
# 7. Launch
# ---------------------------------------------------------------------------
if ($InstallOnly) {
    Log "Step 7/7 skipped (-InstallOnly). Install complete and verified."
    Log "To run later:  .venv\Scripts\Activate.ps1 ; python process_analyzer_allinone.py   (or just rerun install.ps1)"
    exit 0
}
Log "Step 7/7: everything is ready. Launching the analyzer..."
python $PyScript @PyArgs

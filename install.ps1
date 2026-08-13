<#
.SYNOPSIS
    Installe automatiquement tout ce qu'il faut pour faire tourner
    analyseur_processus_allinone.py sur une machine Windows vierge, puis
    lance le script.

.DESCRIPTION
    Ordre des etapes (chacune verifie d'abord si c'est deja present, et ne
    reinstalle rien inutilement) :
      1. Ollama (moteur IA local) - via winget si disponible, sinon
         telechargement direct de l'installeur officiel.
      2. Un modele Ollama adapte a la machine : MEDIUM (llama3:latest,
         ~4,7 Go) sur Windows — la variante MINI (llama3.2:1b) est reservee
         a Android/Termux, gere par install.sh (meme politique de choix).
      3. Python 3 - via winget si disponible, sinon telechargement direct.
      4. Creation + activation d'un environnement virtuel (.venv).
      5. Dependances Python (pip).
      6. Lancement de analyseur_processus_allinone.py.

.NOTES
    Si l'execution de scripts est bloquee par la politique par defaut de
    Windows, lance ce script avec :
        powershell -ExecutionPolicy Bypass -File install.ps1

    Les arguments passes a ce script sont transmis tels quels au script
    Python (ex : .\install.ps1 --no-enrich --max-processes 50).
#>

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PyArgs
)

$ErrorActionPreference = "Continue"

$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyScript     = Join-Path $ScriptDir "analyseur_processus_allinone.py"
$VenvDir      = Join-Path $ScriptDir ".venv"
# Modele MEDIUM (~4,7 Go) — politique par machine : mini (llama3.2:1b) sur
# Android/Termux via install.sh, medium sur macOS/Windows/Linux.
$DefaultModel = "llama3:latest"
$OllamaHost   = "http://localhost:11434"

function Log  ($msg) { Write-Host "`n[install] $msg" -ForegroundColor Cyan }
function Warn ($msg) { Write-Host "[attention] $msg" -ForegroundColor Yellow }
function Err  ($msg) { Write-Host "[erreur] $msg" -ForegroundColor Red }

function Update-SessionPath {
    # Les installeurs (winget, .exe) modifient le PATH machine/utilisateur,
    # jamais celui du processus PowerShell courant : on le recharge pour
    # pouvoir retrouver les binaires fraichement installes sans rouvrir de
    # nouvelle fenetre.
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

if (-not (Test-Path $PyScript)) {
    Err "analyseur_processus_allinone.py introuvable a cote de ce script ($ScriptDir)."
    Err "Place install.ps1 dans le meme dossier que analyseur_processus_allinone.py puis relance."
    exit 1
}

# ---------------------------------------------------------------------------
# 1. Ollama
# ---------------------------------------------------------------------------
Log "Etape 1/5 : verification d'Ollama..."
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd) {
    Log "Ollama deja installe ($($ollamaCmd.Source))."
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Log "Installation d'Ollama via winget..."
        winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Warn "winget a echoue pour Ollama - l'analyse continuera sans IA." }
    } else {
        Log "winget indisponible - telechargement direct de l'installeur Ollama..."
        $installer = Join-Path $env:TEMP "OllamaSetup.exe"
        try {
            Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $installer -UseBasicParsing
            Start-Process -FilePath $installer -ArgumentList "/silent" -Wait
        } catch {
            Warn "Echec du telechargement/installation automatique d'Ollama : $_ - l'analyse continuera sans IA."
        }
    }
    Update-SessionPath
}

$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd) {
    $reachable = $false
    try {
        Invoke-WebRequest -Uri "$OllamaHost/api/tags" -UseBasicParsing -TimeoutSec 2 | Out-Null
        $reachable = $true
    } catch { }
    if (-not $reachable) {
        Log "Demarrage du serveur Ollama en arriere-plan..."
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
    if (-not $reachable) { Warn "Le serveur Ollama ne repond pas encore - l'assistant du script Python proposera de reessayer." }
} else {
    Warn "Ollama n'a pas pu etre installe automatiquement - l'enrichissement IA sera desactive (moteur de risque par regles toujours actif). Installe-le manuellement depuis https://ollama.com/download si besoin."
}

# ---------------------------------------------------------------------------
# 2. Modele Ollama par defaut
# ---------------------------------------------------------------------------
Log "Etape 2/5 : verification du modele Ollama ($DefaultModel)..."
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd) {
    $modelBase = $DefaultModel.Split(":")[0]
    $models = & ollama list 2>$null
    if ($models -match [regex]::Escape($modelBase)) {
        Log "Modele deja present."
    } else {
        Log "Telechargement du modele $DefaultModel (plusieurs Go, peut prendre du temps selon ta connexion)..."
        & ollama pull $DefaultModel
        if ($LASTEXITCODE -ne 0) { Warn "Echec du telechargement du modele - l'analyse continuera sans IA (relance plus tard : ollama pull $DefaultModel)." }
    }
} else {
    Log "Etape ignoree (Ollama indisponible)."
}

# ---------------------------------------------------------------------------
# 3. Python 3
# ---------------------------------------------------------------------------
Log "Etape 3/5 : verification de Python 3..."
$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        $verOut = & $candidate --version 2>&1
        if ($verOut -match "Python 3") { $pythonCmd = $candidate; break }
    }
}

if (-not $pythonCmd) {
    Log "Python 3 introuvable - installation..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Err "winget a echoue pour Python."; exit 1 }
    } else {
        Log "winget indisponible - telechargement direct de l'installeur Python..."
        $installer = Join-Path $env:TEMP "python-installer.exe"
        try {
            Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe" -OutFile $installer -UseBasicParsing
            Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1" -Wait
        } catch {
            Err "Echec du telechargement/installation automatique de Python : $_"
            Err "Installe-le manuellement depuis https://www.python.org/downloads/ puis relance ce script."
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
    Err "Python 3 introuvable meme apres tentative d'installation automatique. Installe-le manuellement depuis https://www.python.org/downloads/ (cocher 'Add python.exe to PATH') puis relance ce script."
    exit 1
}
Log "Python detecte : $(& $pythonCmd --version 2>&1)"

# ---------------------------------------------------------------------------
# 4. Environnement virtuel + activation
# ---------------------------------------------------------------------------
Log "Etape 4/5 : creation de l'environnement virtuel (.venv)..."
if (-not (Test-Path $VenvDir)) {
    & $pythonCmd -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Err "Echec de la creation du venv."
        exit 1
    }
}

$activate = Join-Path $VenvDir "Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Err "Script d'activation introuvable ($activate)."
    exit 1
}
. $activate
Log "Venv actif : $((Get-Command python).Source)"

# ---------------------------------------------------------------------------
# 5. Dependances Python
# ---------------------------------------------------------------------------
Log "Etape 5/5 : installation des dependances Python..."
python -m pip install --upgrade pip --quiet

python -m pip install --quiet psutil networkx matplotlib requests
if ($LASTEXITCODE -ne 0) {
    Warn "Echec via pip standard - nouvelle tentative avec --break-system-packages..."
    python -m pip install --quiet --break-system-packages psutil networkx matplotlib requests
    if ($LASTEXITCODE -ne 0) {
        Err "Echec de l'installation des dependances Python."
        exit 1
    }
}
Log "Dependances installees."

# ---------------------------------------------------------------------------
# Lancement
# ---------------------------------------------------------------------------
Log "Tout est pret. Lancement de l'analyseur..."
python $PyScript @PyArgs

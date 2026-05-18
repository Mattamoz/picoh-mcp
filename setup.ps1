# Picoh-AI one-shot installer for Windows PowerShell.
#
# Re-runnable. See setup.sh for the macOS / Linux equivalent.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $RepoRoot

function Bold($s)   { Write-Host $s -ForegroundColor White }
function Green($s)  { Write-Host $s -ForegroundColor Green }
function Yellow($s) { Write-Host $s -ForegroundColor Yellow }
function Red($s)    { Write-Host $s -ForegroundColor Red }

Bold "=== Picoh-AI setup ==="
Write-Host

# 1. uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Yellow "uv not found — installing from astral.sh..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$HOME\.local\bin;$env:Path"
}
Bold ("uv: " + (uv --version))

# 2. Venv
if (-not (Test-Path .venv)) {
    Bold "Creating .venv (Python 3.12)..."
    uv venv --python 3.12
} else {
    Bold ".venv already exists — reusing"
}

. .\.venv\Scripts\Activate.ps1

# 3. Core install
Bold "Installing picoh-ai + MCP + vision..."
uv pip install -q -e ".[mcp,vision]"

# 4. Picoh hardware driver
python -c "import picoh.picoh" 2>$null
if ($LASTEXITCODE -ne 0) {
    Bold "Installing Picoh hardware driver (no-deps workaround)..."
    uv pip install -q --no-deps picoh
    uv pip install -q pyserial pyttsx3 lxml requests pillow "playsound==1.2.2"
}

Write-Host
Green "Install complete."
Write-Host

# 5. Verify
Bold "Running picoh-mcp --check ..."
Write-Host
picoh-mcp --check
if ($LASTEXITCODE -eq 0) {
    Green "=== Setup verified. ==="
} else {
    Red "=== Setup completed but --check reported issues. ==="
    Write-Host "    (Often this just means Picoh isn't plugged in yet.)"
}

Write-Host
Bold "Next steps:"
Write-Host @"
  1. Plug your Picoh into USB if you haven't already.
  2. Find the absolute path of the picoh-mcp executable:
       where.exe picoh-mcp
  3. Configure your MCP client (Claude Desktop, Claude Code, ChatGPT Desktop, ...)
     to use that path. See MCP_USAGE.md.

  Demo apps you can try now:
       picoh-smoke
       picoh-show
       picoh-mirror
"@

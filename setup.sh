#!/usr/bin/env bash
# Picoh-AI one-shot installer.
#
# What it does:
#   - Ensures `uv` is installed (fast Python package manager)
#   - Creates a Python 3.12 virtual env in ./.venv
#   - Installs picoh-ai + MCP + vision extras
#   - Installs the Picoh hardware driver via the no-deps workaround
#     (avoids playsound's broken Python 3.13+ build)
#   - Runs picoh-mcp --check to verify everything works
#
# Re-run anytime; it's idempotent.

set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

bold()   { printf '\033[1m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
red()    { printf '\033[31m%s\033[0m\n' "$*"; }

bold "=== Picoh-AI setup ==="
echo

# 1. Ensure uv
if ! command -v uv >/dev/null 2>&1; then
  yellow "uv not found — installing it from astral.sh..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Ensure it's on PATH for the rest of this script
  export PATH="$HOME/.local/bin:$PATH"
fi
bold "uv: $(uv --version)"

# 2. Venv
if [ ! -d .venv ]; then
  bold "Creating .venv (Python 3.12)..."
  uv venv --python 3.12
else
  bold ".venv already exists — reusing"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# 3. Core install
bold "Installing picoh-ai + MCP + vision..."
uv pip install -q -e ".[mcp,vision]"

# 4. Picoh hardware driver (with the playsound workaround)
if ! python -c "import picoh.picoh" >/dev/null 2>&1; then
  bold "Installing the Picoh hardware driver (no-deps workaround for playsound)..."
  uv pip install -q --no-deps picoh
  uv pip install -q pyserial pyttsx3 lxml requests pillow "playsound==1.2.2"
fi

echo
green "Install complete."
echo

# 5. Verify
bold "Running picoh-mcp --check ..."
echo
if picoh-mcp --check; then
  echo
  green "=== Setup verified. ==="
else
  echo
  red "=== Setup completed but --check reported issues. See output above. ==="
  echo "    (Often this just means Picoh isn't plugged in yet — try again after plugging it in.)"
fi

echo
bold "Next steps:"
cat <<EOF
  1. Plug your Picoh into USB if you haven't already.
  2. Find the absolute path of the picoh-mcp executable:
       which picoh-mcp
  3. Configure your MCP client (Claude Desktop, Claude Code, ChatGPT Desktop, …)
     to use that path. See MCP_USAGE.md in this folder for full instructions.

  Demo apps you can try now (no AI client needed):
       picoh-smoke       # exercise every channel of the robot
       picoh-show        # a 90-second performance for kids
       picoh-mirror      # face mirroring with the camera
EOF

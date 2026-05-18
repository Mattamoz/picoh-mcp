# Installing Picoh-MCP

This guide walks you through everything you need to put your Ohbot Picoh
"inside" Claude (or any other MCP-aware AI), so that the AI can move it,
change its eye shapes, talk through it, and react to you.

Two install paths are described here:

* **[Path A — clone the repo](#path-a--clone-the-repo)** (recommended for most people)
* **[Path B — download the zip](#path-b--download-the-zip)** (no GitHub account needed; great for classrooms)

Both arrive at the same place: a working `picoh-mcp` command you can point
your AI client at.

> **Heads-up about Python versions.** Picoh's Python driver depends on a
> library (`playsound`) that does not build on Python 3.13+ yet. **Use
> Python 3.10, 3.11, or 3.12.** The instructions below pick a working
> version automatically.

---

## Before you start

You need:

| Thing | Notes |
|---|---|
| Ohbot Picoh robot | https://www.ohbot.co.uk/picoh.html |
| USB cable from Picoh to your computer | The one that came with it |
| A computer running macOS 12+, Windows 10/11, or Linux | |
| An MCP-aware client | Claude Desktop, Claude Code (CLI), ChatGPT Desktop, or another |

That's all. **You do not need an OpenAI or Anthropic API key** for the MCP
server itself — your AI client provides the model. (Other tools in this
project, like `picoh-empath`, do need keys, but the MCP server doesn't.)

---

## Path A — clone the repo

Recommended if you're comfortable opening a terminal. ~5 minutes.

### 1. Install `uv` (a fast Python installer)

This handles the Python version automatically so you don't have to worry
about which Python is installed where.

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Open a new terminal window after installing so `uv` is on your PATH.

### 2. Clone the repository

```bash
git clone https://github.com/<your-username>/picoh-ai.git
cd picoh-ai
```

> Replace `<your-username>` with the actual GitHub owner. If you're reading
> this in the repo itself, the clone URL is the one in the address bar of
> your browser.

### 3. Create a virtual environment and install

```bash
uv venv --python 3.12
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate            # Windows PowerShell

uv pip install -e ".[mcp,vision]"
```

The `[mcp,vision]` extras install the MCP SDK plus MediaPipe (so the
optional vision features work). You can add `[voice,llm]` later if you
want the other apps in this project.

### 4. Install the Picoh hardware driver (special handling)

The official Picoh driver depends on a broken old `playsound` package, so
we install Picoh's *transitive* dependencies one at a time. **Do this once:**

```bash
uv pip install --no-deps picoh
uv pip install pyserial pyttsx3 lxml requests pillow "playsound==1.2.2"
```

### 5. Plug in your Picoh and verify

Plug the USB cable in to both Picoh and your computer.

```bash
picoh-mcp --check
```

You should see a checklist like this:

```
=== picoh-mcp --check ===

1) Importing MCP SDK...
   ok  (FastMCP imported)

2) Connecting to Picoh...
   ok  (HardwarePicoh)

3) Building MCP server + listing tools...
   ok  (10 tools, 3 resources)
      - set_eyes
      - base_colour
      - head_pose
      ...

=== All checks passed. ===
```

If you see "running against MockPicoh" instead of `(HardwarePicoh)`, your
computer isn't seeing the Picoh on USB. See
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### 6. Register the server with your AI client

See [MCP_USAGE.md](MCP_USAGE.md) for the exact config blocks for Claude
Desktop, Claude Code, ChatGPT Desktop, and other MCP clients. The
absolute path you'll need is whatever this prints:

```bash
which picoh-mcp     # macOS / Linux
where.exe picoh-mcp # Windows
```

That's it. Open your AI client, ask it to "set Picoh's eyes to a heart
and turn the base pink", and Picoh should do it.

---

## Path B — download the zip

Use this when you can't (or don't want to) clone from GitHub. Great for
classrooms with several machines.

### 1. Get the zip

Download `picoh-ai.zip` from the source you were given (a USB stick, a
shared drive, an email attachment, or GitHub's *Releases* page).

Unzip it to a folder you'll remember. We'll call it `~/picoh-ai`:

```bash
unzip picoh-ai.zip -d ~/picoh-ai
cd ~/picoh-ai
```

### 2. Run the setup script

The script installs `uv` if needed, creates a `.venv`, installs every
dependency Picoh needs, and runs `picoh-mcp --check` to verify it
worked.

**macOS / Linux:**
```bash
bash setup.sh
```

**Windows (PowerShell):**
```powershell
.\setup.ps1
```

That's it. The script ends with a "Next steps:" panel telling you exactly
what to put into your AI client's MCP config. Follow that, or read
[MCP_USAGE.md](MCP_USAGE.md) for more options.

---

## What's installed (FAQ)

**Q: What got installed on my system?**
Only inside the `.venv/` folder inside the repo / zip. Nothing global.

**Q: How do I uninstall?**
Delete the folder. The whole project is self-contained.

**Q: How do I update later?**
For the cloned repo: `git pull` and re-run `uv pip install -e ".[mcp,vision]"`.
For the zip: download a fresh zip and re-run `setup.sh`.

**Q: I'm on a school computer / locked-down machine.**
Path B's `setup.sh` works without admin rights (it only writes to your
home directory) as long as Python 3.10–3.12 is already installed.

**Q: Will this work with my smart-speaker / phone?**
Not directly. Picoh-MCP needs to run on a computer that's plugged into
the Picoh over USB. But once it's running, any device that's signed into
the same Claude Desktop / ChatGPT Desktop account can talk to it.

---

## Need help?

Read [TROUBLESHOOTING.md](TROUBLESHOOTING.md) first — it covers the seven
most common things that go wrong.

Or open an issue on the GitHub repo with:

* The output of `picoh-mcp --check`
* Your operating system and Python version (`python --version`)
* What you were trying to do when it broke

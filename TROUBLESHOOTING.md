# Troubleshooting

Quick fixes for the seven most common things that go wrong.

> **First step for everything below: run** `picoh-mcp --check`. It will
> tell you which step failed (MCP SDK, Picoh hardware, or tool
> registration) so you know exactly which section here to read.

---

## 1. `--check` says "running against MockPicoh" but I have a real Picoh

This means the picoh Python driver couldn't find the robot on USB.

**Verify the robot is enumerated:**

| OS | Command |
|---|---|
| macOS | `ls /dev/cu.usbmodem*` |
| Linux | `ls /dev/ttyACM* /dev/ttyUSB*` |
| Windows | Open **Device Manager → Ports (COM & LPT)** — Picoh shows up as `Arduino` or `USB Serial Device` |

If nothing shows up:

1. Try a different USB cable. **Many "USB-A to micro-USB" cables are
   power-only and don't carry data** — try the cable that came with Picoh.
2. Try a different USB port. (Direct into your laptop, not via a hub.)
3. Unplug Picoh, wait 5 seconds, plug it back in.

If a port *does* show up but `picoh-mcp --check` still falls back to mock,
explicitly tell picoh-ai which port to use. Edit `.env` in the project
root (copy `.env.example` if you don't have one):

```
PICOH_PORT=/dev/cu.usbmodem4101   # macOS / Linux
PICOH_PORT=COM3                    # Windows
```

Then re-run `picoh-mcp --check`.

---

## 2. "playsound" or "could not get source code" install error

This is a known compatibility issue between Picoh's pinned `playsound`
package and Python 3.13+.

**Fix:** use Python 3.10, 3.11, or 3.12. With `uv`:

```bash
rm -rf .venv
uv venv --python 3.12
source .venv/bin/activate
uv pip install --no-deps picoh
uv pip install pyserial pyttsx3 lxml requests pillow "playsound==1.2.2"
uv pip install -e ".[mcp,vision]"
```

The `--no-deps picoh` + manual install of its transitive deps avoids
ever resolving the broken modern `playsound`.

---

## 3. `picoh.say` is silent (no voice comes out)

The picoh library uses your operating system's text-to-speech.

**macOS:** Open **System Settings → Accessibility → Spoken Content →
System Voice → Manage Voices**. Make sure at least one English voice is
fully downloaded (not a cloud voice). On recent macOS, certain "premium"
voices show up before they're downloaded — pick a non-premium one until
the download finishes.

You can test outside picoh-ai:
```bash
say "Hello world"
```
If that's silent too, it's a macOS voice issue, not a Picoh issue.

**Linux:** picoh uses `espeak-ng` via `pyttsx3`. Install it:
```bash
sudo apt-get install espeak-ng
```

**Windows:** Use the built-in SAPI voices via Settings → Time & Language
→ Speech.

---

## 4. Eyes look like a line, a U-shape, or are very dim

Two possible causes, both fixed in current code but worth knowing if you
ever see it again:

* **LIDBLINK convention.** Picoh's eyelid motor uses `10 = open, 0 =
  closed`. Any code that has `move(LIDBLINK, 0)` to "open" the eyes has
  it backwards.
* **EYETILT range.** EYETILT controls which sub-frame of the multi-frame
  eye-shape hex is rendered. If it goes outside ~3.5–6.5, the pupil
  "looks off the edge" and you see a thin line.

If you're writing your own prompts, ask the AI to call
`gesture("neutral")` or `reset()` to put things back to known-good
defaults.

---

## 5. MCP client doesn't see the server

After registering the server in (e.g.) Claude Desktop:

1. **Did you fully quit and re-launch?** Reload-with-cmd-R isn't enough.
   On macOS: Cmd-Q, then re-open. On Windows: right-click the system tray
   icon → Quit, then re-open.
2. **Is the path absolute?** Relative paths and `~` don't work in MCP
   configs. Use `which picoh-mcp` (or `where.exe picoh-mcp` on Windows)
   to get an absolute path.
3. **Does the path actually exist?** Open a terminal and run that path
   with `--check`:
   ```bash
   /the/absolute/path/to/picoh-mcp --check
   ```
   If the path doesn't run from the terminal, it won't run from the
   MCP client either.

In Claude Desktop, you can confirm the server connected: click the small
🔌 icon in the chat input — you should see `picoh` listed with 10 tools.
If you see "Failed", click "Show logs" for the actual error.

---

## 6. Camera permission denied (vision-based features)

The MCP server itself doesn't need a camera, but if you also run the
empath / mirror / show apps, MediaPipe needs camera access.

**macOS:** When OpenCV first asks for camera access, the request might
not show a dialog (a known AVFoundation quirk). Granting it manually:

1. Open **System Settings → Privacy & Security → Camera**.
2. Find the app launching the Python process — that might be
   `Terminal`, `iTerm`, `VS Code`, or the AI client itself.
3. Toggle it on.
4. Restart that app.

If still failing, set `OPENCV_AVFOUNDATION_SKIP_AUTH=1` in your
environment before running the app:
```bash
OPENCV_AVFOUNDATION_SKIP_AUTH=1 picoh-mirror
```

---

## 7. Picoh disconnects from USB during a long session

Usually a power or cable issue. Symptoms:

* Mid-session, motors stop responding
* `picoh.connected` becomes False without warning
* USB device disappears from `/dev/cu.usbmodem*`

**Recovery:**
1. Unplug Picoh from USB.
2. Wait 5 seconds.
3. Plug it back in.
4. Restart the MCP server (and the AI client, if it cached the
   connection).

**Prevention:**
* Use a powered USB hub if your laptop is short on power.
* Use the original cable.
* Don't call `picoh.close()` and `picoh.init()` repeatedly in the same
  process — some firmware builds get confused.

---

## Still stuck?

Run `picoh-mcp --check` and capture its full output. Open an issue with:

* `picoh-mcp --check` output
* OS + version (`uname -a` on macOS/Linux, `winver` on Windows)
* Python version (`python --version`)
* Output of `pip list | grep -i -E 'picoh|mcp|mediapipe'`
* What you were trying to do
* What you expected vs. what happened

Most fixes turn out to be one of the seven cases above, but real bugs do
exist — please report them.

# Using Picoh-MCP

Once installed (see [INSTALL.md](INSTALL.md)), Picoh-MCP exposes the
robot's body as **tools** that any MCP-aware AI can call. This guide
shows you:

1. [How to register the server](#registering-the-server) in Claude
   Desktop, Claude Code, ChatGPT Desktop, and any other MCP client.
2. [The full tool catalogue](#tool-catalogue).
3. [Prompts to copy and paste](#example-prompts) once it's wired up.

---

## Finding the executable path

Every MCP client needs the **absolute path** to the `picoh-mcp` command
that was installed in your virtual environment. Get it with:

**macOS / Linux:**
```bash
source .venv/bin/activate    # if not already active
which picoh-mcp
```

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\activate
where.exe picoh-mcp
```

That prints something like
`/Users/you/picoh-ai/.venv/bin/picoh-mcp` (macOS) or
`C:\Users\you\picoh-ai\.venv\Scripts\picoh-mcp.exe` (Windows).

Copy that path; you'll paste it into one of the config blocks below.

---

## Registering the server

### Claude Desktop

1. Open Claude Desktop → **Settings** → **Developer** → **Edit Config**.
   That opens `claude_desktop_config.json` in your editor.

   The file lives at:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. Add (or merge) this block:

   ```json
   {
     "mcpServers": {
       "picoh": {
         "command": "/absolute/path/to/.venv/bin/picoh-mcp"
       }
     }
   }
   ```

   Windows path example:
   ```json
   {
     "mcpServers": {
       "picoh": {
         "command": "C:\\Users\\you\\picoh-ai\\.venv\\Scripts\\picoh-mcp.exe"
       }
     }
   }
   ```

3. **Fully quit and restart Claude Desktop** (it doesn't pick up MCP
   config changes on reload). After restart you should see a small 🔌
   hammer-and-screwdriver icon in the chat box; clicking it shows
   "picoh" with 10 tools.

### Claude Code (CLI)

If you have the `claude` CLI installed:

```bash
claude mcp add picoh /absolute/path/to/.venv/bin/picoh-mcp
```

Verify with:

```bash
claude mcp list
```

Picoh's tools are now usable in any Claude Code session — e.g. add a
`Stop` hook that has Claude nod or shake based on the test result.

### ChatGPT Desktop

ChatGPT Desktop's **Connectors** UI accepts local MCP servers via the
same stdio protocol:

1. Open ChatGPT Desktop → **Settings** → **Connectors** → **Add custom MCP**.
2. **Name:** `picoh`
3. **Command:** the absolute path from `which picoh-mcp` above.
4. Restart the app.

### Any other MCP client (Goose, Cursor, Continue, Windsurf, your own…)

Any client that follows the standard MCP stdio protocol can run this
server. The minimum it needs to know is:

- **Command:** absolute path to `picoh-mcp`
- **Args:** none
- **Transport:** stdio

There is no authentication. There are no environment variables that must
be set (apart from `PICOH_PORT` if your Picoh is on a non-default serial
port — see TROUBLESHOOTING.md).

If your client supports MCP environment variables and you want to run
against the in-process mock without hardware:

```json
{
  "command": "/path/to/picoh-mcp",
  "env": { "PICOH_MOCK": "1" }
}
```

---

## Tool catalogue

These are the **tools** Picoh-MCP exposes. The AI calls them by name,
just like any other MCP server. You can list them yourself at any time:

```bash
picoh-mcp --tools
```

| Tool | Args | What it does |
|---|---|---|
| `set_eyes` | `left`, `right` | Set the 8×8 LED eye shapes. Names: `Angry`, `BoxLeft`, `BoxRight`, `Crying`, `Eyeball`, `Full`, `Glasses`, `Heart`, `Large`, `Sad`, `SmallBall`, `Square`, `SunGlasses`, `VerySad`. |
| `base_colour` | `r`, `g`, `b` (0–10 each) | Set the RGB base light under Picoh. |
| `head_pose` | `nod`, `turn`, `tilt`, `speed` (all 0–10) | Pose the head. Any axis may be omitted; 5 is centred. |
| `look` | `x`, `y`, `speed` (0–10) | Eye saccade (no head movement). `y` is clamped to a safe pupil range so the LED pattern stays clean. |
| `gesture` | `name` | Run a composite gesture: `nod_yes`, `shake_no`, `double_take`, `sigh`, `lean_in`, `sleep`, `wake_up`, `excited`, `think`, `love`, `confused`, `neutral`. |
| `move` | `motor`, `pos`, `speed` | Low-level motor: `HEADNOD`, `HEADTURN`, `EYETURN`, `LIDBLINK`, `BOTTOMLIP`, `EYETILT`, `TOPLIP`. |
| `say` | `text` | Speak with built-in lip-sync. Blocks until done. Uses your OS's text-to-speech voice. |
| `play_sound` | `name` | Play a WAV from `picohData/Sounds/` (built-ins: `fanfare`, `loop`, `ohbot`, `smash`, `spring`). |
| `read_sensor` | `pin` (0–6) | Read one of the analog input pins (0–10). |
| `reset` | — | Return Picoh to a neutral resting pose. |

There are also **resources** the AI can read for self-discovery:

- `picoh://state/eyes` — the list of valid eye shapes
- `picoh://state/gestures` — the list of valid gestures
- `picoh://state/motors` — the list of valid motor names

---

## Example prompts

Once the server is registered, just talk to your AI client about Picoh.
Try these to get a feel for what's possible:

### Basic expression

> Picoh, say hello and put a heart on each eye while turning the base pink.

> Picoh, look surprised — open your eyes wide, change colour to orange,
> and do a double-take.

### Reactions

> When I tell you a joke, react with the appropriate face. Picoh should
> roll its eyes at bad puns and laugh at good ones. *Ready?* Why did the
> chicken cross the road?

> I'll read out test results. Picoh should nod and turn green when a test
> passes, shake its head and turn red when one fails.

### Performance

> Picoh, do a 15-second dance routine using head movements, eye-shape
> changes, and rainbow base colours synchronised to an imaginary beat.

> Picoh, perform a quick "wake up from a nap" routine — start with eyes
> closed and base off, then yawn (open mouth), stretch, blink, and
> finally look around the room.

### Story / character

> Pretend Picoh is a grumpy old wizard. Give it a one-paragraph
> introduction in character, using `say`, with grumpy eye shapes and a
> stormy base colour.

> Picoh is now a friendly tour guide for our office. Welcome a visitor
> named Sam — set eye shapes and gestures so it feels like a real greeting.

### Interactive

> Picoh, every time I say "hello" you should nod and say "Hi there!".
> Every time I say "goodbye" you should wave (you don't have arms — use
> head turns) and say "See you soon!".

> Read me a bedtime story for kids, one paragraph at a time, with Picoh
> acting out the characters — change voice tone (via the words you write
> for `say`), eye shapes, and base colours.

### Useful

> Whenever I get a new email (assume I'll tell you), check the sender and
> have Picoh react — flash green for important people, sigh and turn
> orange for marketing, ignore newsletters.

> Be my standup-meeting timer. For each 60-second slot, Picoh should
> count down with subtle colour changes (cool blue at start, warm
> red-orange near the end), then say "Time's up!" and nod.

---

## Tips for great Picoh interactions

* **Tell the model to use its body.** Without prompting, Claude will often
  just `say(...)` everything. Adding "*react with eye shapes and head
  movements between sentences*" makes a huge difference.

* **Combine tools per turn.** A great Picoh moment usually combines an eye
  shape + a base colour + a small head movement + a short spoken line.
  Models do this naturally once you ask for it.

* **`say` blocks.** While Picoh is speaking, no other tool will run.
  Keep individual lines short for snappy reactions.

* **`reset` between scenes.** If you've been telling Picoh to do a lot,
  ask the AI to `reset` between activities so it starts from neutral.

* **Don't overdrive the eyes.** Calling `look` very rapidly looks jittery.
  Once or twice a second is plenty.

---

## What can go wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| Tools appear but nothing happens on Picoh | Server is using MockPicoh | `picoh-mcp --check` — see [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| AI client doesn't see the server | Config block in wrong file, or client wasn't fully quit + relaunched | Check the absolute path in `command:` and restart the client |
| Eyes look like a line or U-shape | Older version of this code | Pull latest — fixed in v0.1.0 |
| Picoh is silent when asked to `say` | macOS voice not downloaded | System Settings → Accessibility → Spoken Content → System voice → Manage Voices |
| Picoh disappears from USB during a long session | Cable or power glitch | Unplug + replug, then restart your AI client |

Full troubleshooting in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

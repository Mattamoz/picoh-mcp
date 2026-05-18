# picoh-ai

**AI superpowers for the [Ohbot Picoh](https://www.ohbot.co.uk/picoh.html) desktop robot.**

The headline feature is **`picoh-mcp`** — a Model Context Protocol (MCP)
server that exposes Picoh's body as tools for any MCP-aware AI. Add it
to Claude Desktop, Claude Code, ChatGPT Desktop (or any other MCP client)
and you can suddenly tell *any* AI things like:

> *"Picoh, react sadly when I tell you a joke, then snap out of it on the punchline."*
> *"Picoh, nod every time my test suite passes."*
> *"Picoh, perform a 15-second wake-up routine — yawn, blink, look around, then greet me."*

…and it just works.

The same repo also ships four ready-to-run demo apps for use *without*
needing to wire up an MCP client (see [Demo apps](#demo-apps)).

---

## What is this for?

* **Teachers, kids, classrooms** — Picoh becomes a character that *any*
  AI you have access to can voice and animate. Run `picoh-show` for a
  90-second performance straight out of the box.

* **Developers** — A worked example of how to wrap a piece of hardware
  as an MCP server, plus a working OpenAI Realtime client, a MediaPipe
  vision pipeline, and a Claude-driven theatre director, all sharing
  one embodiment layer.

* **Anyone with a Picoh on their desk** — Stop programming Picoh in
  Scratch-with-Python and start *talking* to it through the AI you
  already use every day.

---

## Get started in 5 minutes

If you have a Picoh plugged in and a terminal open:

```bash
git clone https://github.com/chrismeah/picoh-ai.git
cd picoh-ai
bash setup.sh        # creates .venv, installs everything, runs picoh-mcp --check
```

When `--check` passes, point your AI client at the server. Full per-client
instructions are in **[MCP_USAGE.md](MCP_USAGE.md)**.

Full step-by-step (including Windows + classrooms-without-git) is in
**[INSTALL.md](INSTALL.md)**.

If something breaks, see **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**.

---

## What's inside

### The MCP server (the headline feature)

`picoh-mcp` exposes Picoh's body as 10 tools any MCP client can call:

```
set_eyes(left, right)               base_colour(r, g, b)
head_pose(nod, turn, tilt, speed)   look(x, y, speed)
gesture(name)                       move(motor, pos, speed)
say(text)                           play_sound(name)
read_sensor(pin)                    reset()
```

Plus three resources (`picoh://state/eyes`, `…/gestures`, `…/motors`)
so the AI can self-discover what's valid. Full reference + example
prompts in [MCP_USAGE.md](MCP_USAGE.md).

The server is built on the [official FastMCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).

### Demo apps

These run on their own — no MCP client required. Every one supports
`--mock` so it'll run with no hardware (useful for development).

| Command | What it does |
|---|---|
| `picoh-smoke`     | Exercises every embodiment channel end-to-end. Run after install. |
| `picoh-show`      | A 90-second 5-act performance for kids: wake-up, emotions, face-tracking, copycat game, disco. Just needs a webcam. |
| `picoh-mirror`    | 30 fps face mirroring — Picoh follows your head/mouth/blinks in real time. No keys. |
| `picoh-empath`    | Realtime voice + vision companion using OpenAI's Realtime API. Picoh's expressions, head movements, and base light are all model-driven tool calls. Needs `OPENAI_API_KEY`. |
| `picoh-theatre`   | A one-robot theatre. Claude Sonnet directs; OpenAI TTS performs; MediaPipe reads the audience and the story branches accordingly. Needs `OPENAI_API_KEY` + `ANTHROPIC_API_KEY`. |
| `picoh-companion` | An autonomous desk pet. Three-loop reflex/perception/cognition architecture with persistent JSON memory. Needs `ANTHROPIC_API_KEY`. |

### The library

If you want to build your own Picoh apps, import from `picoh_ai`:

```python
from picoh_ai.embodiment import Embodiment
from picoh_ai.gestures import perform
from picoh_ai.vision import VisionSensor
from picoh_ai.idle import IdleLoop

with Embodiment.connect() as emb:
    IdleLoop(emb).start()              # auto blinks, breathing, saccades
    emb.set_eyes("Heart")
    emb.base_colour(10, 0, 5)
    perform(emb, "nod_yes")
    emb.say("Hi!")
```

The `MockPicoh` backend means the same code runs on machines with no
robot attached — every action just prints what it would have done.

---

## Architecture

```
                ┌──────────────────────────────────────────────────────┐
                │                       apps/                          │
                │  empath   picoh_mcp   mirror   theatre   companion   │
                │                       show                           │
                └────┬────────────┬────────┬────────┬────────┬─────────┘
                     │            │        │        │        │
              ┌──────▼────┐  ┌────▼────┐ ┌─▼──┐  ┌──▼────┐ ┌─▼───────────┐
              │ realtime  │  │ FastMCP │ │ -  │  │ Claude│ │ Claude+queue│
              │  client   │  │ server  │ │    │  │ +TTS  │ │ + memory    │
              └─────┬─────┘  └────┬────┘ └─┬──┘  └───┬───┘ └─────┬───────┘
                    │             │        │         │           │
              ┌─────▼─────────────▼────────▼─────────▼───────────▼─────┐
              │                       tools.py                          │
              │   one schema → OpenAI Realtime + MCP, one dispatch      │
              └────────────────────────────┬─────────────────────────────┘
                                           │
                                ┌──────────▼──────────┐
                                │   embodiment.py     │ ←── idle.py (30 Hz)
                                │  hardware OR mock   │      breaths, blinks,
                                │  + gestures.py      │      micro-saccades
                                └──────────┬──────────┘
                                           │
                                       Picoh USB
                                       (or stdout in mock mode)
```

One schema in `tools.py` is the single source of truth for what Picoh
can do. Both the OpenAI Realtime `session.update` and the FastMCP server
consume the same catalogue, so the model's mental model of Picoh's body
is identical no matter how you talk to it.

---

## Tests

```bash
PICOH_MOCK=1 pytest -q
```

45 tests covering embodiment, gestures, tool dispatch, idle loop, memory,
and vision categorisation. All run against `MockPicoh`, so no hardware
needed.

---

## Compatibility

| Component | Tested versions |
|---|---|
| Picoh | All hardware revisions supported by `picoh-python==1.276` |
| Python | 3.10, 3.11, 3.12 *(3.13+ blocked by `playsound` until upstream fixes)* |
| OS | macOS 13+, Ubuntu 22.04+, Windows 10/11 |
| MCP clients | Claude Desktop, Claude Code, ChatGPT Desktop, any stdio-MCP client |
| Realtime / Theatre | OpenAI `gpt-realtime` family + `gpt-4o-mini-tts` |
| Companion / Theatre director | Claude Sonnet 4.6, Claude Haiku 4.5 |

---

## License

MIT. See [LICENSE](LICENSE).

Picoh hardware is © Ohbot Ltd; this project is not affiliated with Ohbot.

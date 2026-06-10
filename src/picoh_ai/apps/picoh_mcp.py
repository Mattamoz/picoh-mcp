"""Picoh-MCP — expose Picoh as an MCP server.

Run as a stdio MCP server (default):

    picoh-mcp

Self-test commands (no MCP client required):

    picoh-mcp --check          # verify Picoh hardware + tool registration
    picoh-mcp --tools          # print the full tool catalogue
    picoh-mcp --mock           # use MockPicoh (no hardware) - useful for dev

Register the server with an MCP client by pointing it at the absolute path
of the installed ``picoh-mcp`` console script. Per-client snippets are in
``MCP_USAGE.md``.
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from ..embodiment import EYE_SHAPES, MOTORS, Embodiment
from ..gestures import GESTURE_NAMES, perform
from ..idle import IdleLoop


# --------------------------------------------------------------------------- #
# Server build
# --------------------------------------------------------------------------- #

def _build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as e:  # pragma: no cover
        print(
            f"FATAL: MCP SDK not installed ({e}). Run:\n"
            f"   pip install 'picoh-ai[mcp]'  or  uv pip install 'mcp[cli]'",
            file=sys.stderr,
        )
        raise

    load_dotenv()
    emb = Embodiment.connect()
    idle = IdleLoop(emb).start()
    print(f"[picoh-mcp] embodiment ready (mock={emb.mocked})", file=sys.stderr)

    mcp = FastMCP("picoh")

    @mcp.tool()
    def set_eyes(left: str, right: str) -> str:
        f"""Set Picoh's left and right eye LED shapes. Valid: {', '.join(EYE_SHAPES)}."""
        idle.wake()
        idle.inhibit(0.5)
        emb.set_eyes(left, right)
        return "ok"

    @mcp.tool()
    def base_colour(r: int, g: int, b: int) -> str:
        """Set Picoh's RGB base light (each channel 0-10)."""
        idle.wake()
        emb.base_colour(r, g, b)
        return "ok"

    @mcp.tool()
    def head_pose(nod: float | None = None, turn: float | None = None,
                  tilt: float | None = None, speed: float = 5) -> str:
        """Pose Picoh's head. nod/turn/tilt each 0-10. speed 0-10."""
        idle.wake()
        idle.inhibit(0.6)
        emb.head_pose(nod=nod, turn=turn, tilt=tilt, speed=speed)
        return "ok"

    @mcp.tool()
    def look(x: float, y: float, speed: float = 8) -> str:
        """Saccade — eyes only — to position (x,y) each 0-10."""
        idle.wake()
        idle.inhibit(0.5)
        emb.look(x, y, speed)
        return "ok"

    @mcp.tool()
    def gesture(name: str) -> str:
        f"""Run a named composite gesture. Valid: {', '.join(GESTURE_NAMES)}."""
        idle.wake()
        idle.inhibit(1.5)
        perform(emb, name)
        return "ok"

    @mcp.tool()
    def move(motor: str, pos: float, speed: float = 5) -> str:
        f"""Low-level motor move. motor in {', '.join(MOTORS)}, pos/speed 0-10."""
        idle.wake()
        idle.inhibit(0.6)
        emb.move(motor, pos, speed)
        return "ok"

    @mcp.tool()
    def say(text: str) -> str:
        """Speak ``text`` with built-in lip-sync. Blocks until done."""
        idle.wake()
        idle.inhibit(max(1.0, 0.4 * len(text.split())))
        # Try stopping blocking so that movement can continue.  As the picoh library starts a thread for lipsynch this should be fine although it may fail if a second phrase is sent
        emb.say(text, until_done=False, lip_sync=True)
        return "ok"

    @mcp.tool()
    def play_sound(name: str) -> str:
        """Play a WAV from picohData/Sounds (e.g. fanfare, ohbot)."""
        idle.wake()
        emb.play_sound(name)
        return "ok"

    @mcp.tool()
    def read_sensor(pin: int) -> float:
        """Read analog sensor pin 0-6, returns 0-10."""
        return emb.read_sensor(pin)

    @mcp.tool()
    def reset() -> str:
        """Return Picoh to a neutral resting pose."""
        idle.wake()
        idle.inhibit(2.0)
        emb.reset()
        return "ok"

    @mcp.resource("picoh://state/eyes")
    def list_eyes() -> str:
        """All valid eye shape names."""
        return ", ".join(EYE_SHAPES)

    @mcp.resource("picoh://state/gestures")
    def list_gestures() -> str:
        """All valid gesture names."""
        return ", ".join(GESTURE_NAMES)

    @mcp.resource("picoh://state/motors")
    def list_motors() -> str:
        """All valid motor names."""
        return ", ".join(MOTORS)

    return mcp, emb


# --------------------------------------------------------------------------- #
# Self-test entry points
# --------------------------------------------------------------------------- #

def _cmd_check(args) -> int:
    """Verify hardware + tool registration. Prints a checklist, returns 0/1."""
    import asyncio

    failures = 0

    print("\n=== picoh-mcp --check ===\n")
    print("1) Importing MCP SDK...")
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: F401
        print("   ok  (FastMCP imported)\n")
    except Exception as e:
        print(f"   FAIL: {e}")
        print("        Install with: pip install 'mcp[cli]'\n")
        return 1

    print("2) Connecting to Picoh...")
    try:
        emb = Embodiment.connect()
        if emb.mocked:
            print("   warn: running against MockPicoh (no hardware found)")
            print("         The MCP server will still work but no robot will move.")
            print("         Set PICOH_PORT in .env or plug in your Picoh.")
        else:
            print(f"   ok  ({type(emb.backend).__name__})")
        emb.close()
    except Exception as e:
        print(f"   FAIL: {e}\n")
        failures += 1

    print("\n3) Building MCP server + listing tools...")
    try:
        mcp, emb2 = _build_server()
        emb2.close()

        async def _list():
            tools = await mcp.list_tools()
            resources = await mcp.list_resources()
            return tools, resources

        tools, resources = asyncio.run(_list())
        print(f"   ok  ({len(tools)} tools, {len(resources)} resources)")
        for t in tools:
            print(f"      - {t.name}")
        for r in resources:
            print(f"      - resource: {r.uri}")
    except Exception as e:
        print(f"   FAIL: {e}")
        failures += 1

    print()
    if failures:
        print(f"=== {failures} failure(s). Fix the issues above before configuring an MCP client. ===\n")
        return 1
    print("=== All checks passed. You can register this server with your MCP client now. ===")
    print("    See MCP_USAGE.md for client-specific config snippets.\n")
    return 0


def _cmd_tools(args) -> int:
    """Print the full tool catalogue + example prompts."""
    print("\n=== picoh-mcp — tool catalogue ===\n")
    print("Tools the MCP server exposes (every MCP-aware client can call these):\n")

    cat = [
        ("set_eyes(left, right)",
         f"Set the 8x8 LED eye shapes. left/right ∈ {{{', '.join(EYE_SHAPES)}}}."),
        ("base_colour(r, g, b)",
         "Set the RGB base light. Each channel 0–10."),
        ("head_pose(nod, turn, tilt, speed=5)",
         "Pose the head. Each axis 0–10 (5 = centre). speed 0–10."),
        ("look(x, y, speed=8)",
         "Saccade — eyes only — to (x, y), each 0–10."),
        ("gesture(name)",
         f"Run a composite gesture: {', '.join(GESTURE_NAMES)}."),
        ("move(motor, pos, speed=5)",
         f"Raw motor move. motor ∈ {{{', '.join(MOTORS)}}}, pos/speed 0–10."),
        ("say(text)",
         "Speak with built-in lip-sync. Blocks until finished."),
        ("play_sound(name)",
         "Play a WAV file from picohData/Sounds (e.g. fanfare, ohbot)."),
        ("read_sensor(pin)",
         "Read analog sensor pin 0–6. Returns 0–10."),
        ("reset()",
         "Return Picoh to a neutral resting pose."),
    ]
    for sig, desc in cat:
        print(f"  {sig}")
        print(f"      {desc}\n")

    print("Try these prompts in your MCP client (Claude Desktop, Claude Code, etc.):\n")
    examples = [
        "Picoh, say hello and put a heart on each eye.",
        "Picoh, look surprised when I say 'boo'.",
        "Picoh, do a 10-second dance routine using gestures and colour changes.",
        "Picoh, pretend to be sad, then cheer up over the next 5 seconds.",
        "Picoh, follow my voice — nod yes when I make a statement, shake no when I ask a question.",
        "Picoh, read out the weather and react with appropriate eyes and base colour.",
        "Picoh, give me a 5-second hype reaction when I tell you my PR landed.",
    ]
    for ex in examples:
        print(f'  • "{ex}"')
    print()
    return 0


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="picoh-mcp",
        description=(
            "MCP server that lets any MCP-aware AI (Claude Desktop, Claude "
            "Code, ChatGPT desktop, etc.) drive an Ohbot Picoh robot."
        ),
    )
    parser.add_argument("--mock", action="store_true",
                        help="Force MockPicoh (no hardware needed)")
    parser.add_argument("--check", action="store_true",
                        help="Run a self-test and exit (verify SDK + Picoh + tools)")
    parser.add_argument("--tools", action="store_true",
                        help="Print the full tool catalogue + example prompts and exit")
    parser.add_argument("--version", action="version", version=f"picoh-mcp {_pkg_version()}")
    args = parser.parse_args()

    if args.mock:
        os.environ["PICOH_MOCK"] = "1"

    if args.tools:
        sys.exit(_cmd_tools(args))
    if args.check:
        sys.exit(_cmd_check(args))

    mcp, _emb = _build_server()
    mcp.run(transport="stdio")


def _pkg_version() -> str:
    try:
        from importlib.metadata import version
        return version("picoh-ai")
    except Exception:
        return "0.1.0"


if __name__ == "__main__":
    main()

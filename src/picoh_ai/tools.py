"""Shared tool catalogue used by **both** the OpenAI Realtime API
(``empath``) and the FastMCP server (``picoh_mcp``).

Defining tools in one place gets us two important properties:

1. The model's mental model of Picoh's body is *identical* whether you talk
   to it through realtime voice, Claude Desktop's MCP UI, or anything else.
2. The dispatcher below is the only place that maps a (name, arg-dict) into
   an actual embodiment call. New tools = add an entry to ``CATALOG`` and a
   case in ``dispatch``. No N×M wiring per app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .embodiment import EYE_SHAPES, MOTORS, Embodiment
from .gestures import GESTURE_NAMES, perform


# --------------------------------------------------------------------------- #
# Schema model
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema

    def to_openai_realtime(self) -> dict[str, Any]:
        # Realtime API "function" tool shape (top-level type=function)
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #

def _enum(values) -> dict:
    return {"type": "string", "enum": list(values)}


CATALOG: list[Tool] = [
    Tool(
        name="set_eyes",
        description=(
            "Change Picoh's 8x8 LED eye shapes. Use this *frequently* to express "
            "emotion alongside speech (Heart for affection, Sad for empathy, "
            "SunGlasses for swagger, Eyeball is the neutral default)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "left": _enum(EYE_SHAPES),
                "right": _enum(EYE_SHAPES),
            },
            "required": ["left", "right"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="base_colour",
        description=(
            "Set Picoh's RGB base light (0-10 each). Use to set ambient mood: "
            "warm orange/red for energy, cool blue/green for calm, off for sleep."
        ),
        parameters={
            "type": "object",
            "properties": {
                "r": {"type": "integer", "minimum": 0, "maximum": 10},
                "g": {"type": "integer", "minimum": 0, "maximum": 10},
                "b": {"type": "integer", "minimum": 0, "maximum": 10},
            },
            "required": ["r", "g", "b"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="head_pose",
        description=(
            "Pose Picoh's head. Values 0-10. Defaults to 5 (centered) if omitted. "
            "speed 0-10 (default 5). Use *small* changes around 5 to feel natural."
        ),
        parameters={
            "type": "object",
            "properties": {
                "nod":   {"type": "number", "minimum": 0, "maximum": 10},
                "turn":  {"type": "number", "minimum": 0, "maximum": 10},
                "tilt":  {"type": "number", "minimum": 0, "maximum": 10},
                "speed": {"type": "number", "minimum": 0, "maximum": 10},
            },
            "additionalProperties": False,
        },
    ),
    Tool(
        name="look",
        description="Saccade — move only the eyes to x,y (0-10).",
        parameters={
            "type": "object",
            "properties": {
                "x":     {"type": "number", "minimum": 0, "maximum": 10},
                "y":     {"type": "number", "minimum": 0, "maximum": 10},
                "speed": {"type": "number", "minimum": 0, "maximum": 10},
            },
            "required": ["x", "y"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="gesture",
        description=(
            "Trigger a named composite gesture. nod_yes/shake_no for direct "
            "answers; double_take for surprise; sigh for resignation; lean_in "
            "to show focused attention; think while computing; love/excited "
            "for big positive reactions; confused when unsure; neutral to "
            "return to rest; sleep/wake_up are persistent state changes."
        ),
        parameters={
            "type": "object",
            "properties": {"name": _enum(GESTURE_NAMES)},
            "required": ["name"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="move",
        description=(
            "Low-level: move a specific motor to position 0-10 at speed 0-10. "
            "Prefer head_pose/look/gesture when possible."
        ),
        parameters={
            "type": "object",
            "properties": {
                "motor": _enum(MOTORS),
                "pos":   {"type": "number", "minimum": 0, "maximum": 10},
                "speed": {"type": "number", "minimum": 0, "maximum": 10},
            },
            "required": ["motor", "pos"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="say",
        description=(
            "Speak text with built-in lip-sync. Picoh's mouth moves automatically. "
            "Use only when you specifically need Picoh's local TTS voice; in the "
            "Empath app you should usually just stream voice directly."
        ),
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="play_sound",
        description="Play a WAV from picohData/Sounds (e.g. fanfare, loop, ohbot, smash, spring).",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    ),
    Tool(
        name="read_sensor",
        description="Read analog sensor pin 0-6, returns 0-10.",
        parameters={
            "type": "object",
            "properties": {"pin": {"type": "integer", "minimum": 0, "maximum": 6}},
            "required": ["pin"],
            "additionalProperties": False,
        },
    ),
]


CATALOG_BY_NAME: dict[str, Tool] = {t.name: t for t in CATALOG}


def openai_realtime_tools() -> list[dict[str, Any]]:
    return [t.to_openai_realtime() for t in CATALOG]


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #

def dispatch(emb: Embodiment, name: str, args: dict[str, Any]) -> Any:
    """Execute a tool call against the embodiment. Returns a small JSON-safe
    response that the LLM can read back as ``function_call_output``.
    """
    args = args or {}

    if name == "set_eyes":
        emb.set_eyes(args["left"], args["right"])
        return {"ok": True}

    if name == "base_colour":
        emb.base_colour(args["r"], args["g"], args["b"])
        return {"ok": True}

    if name == "head_pose":
        emb.head_pose(
            nod=args.get("nod"),
            turn=args.get("turn"),
            tilt=args.get("tilt"),
            speed=args.get("speed", 5),
        )
        return {"ok": True}

    if name == "look":
        emb.look(args["x"], args["y"], speed=args.get("speed", 8))
        return {"ok": True}

    if name == "gesture":
        perform(emb, args["name"])
        return {"ok": True}

    if name == "move":
        emb.move(args["motor"], args["pos"], args.get("speed", 5))
        return {"ok": True}

    if name == "say":
        emb.say(args["text"])
        return {"ok": True}

    if name == "play_sound":
        emb.play_sound(args["name"])
        return {"ok": True}

    if name == "read_sensor":
        return {"value": emb.read_sensor(args["pin"])}

    return {"ok": False, "error": f"unknown tool {name!r}"}


def make_dispatcher(emb: Embodiment) -> Callable[[str, dict[str, Any]], Any]:
    """Bind dispatch to a specific embodiment so callers pass (name, args) only."""
    def _call(name: str, args: dict[str, Any]) -> Any:
        return dispatch(emb, name, args)
    return _call

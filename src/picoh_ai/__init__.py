"""picoh-ai — AI superpowers for the Ohbot Picoh.

Layout:
    embodiment        Thin, mockable wrapper over the picoh library.
    tools             Shared tool schemas (OpenAI Realtime + MCP).
    gestures          Composite named gestures (nod_yes, sigh, double_take...).
    idle              Background micro-behaviour loop (blinks, breathing, drift).
    vision            MediaPipe + DeepFace background sensor.
    audio_io          Mic / speaker streaming for the Realtime API.
    realtime_client   Async OpenAI Realtime WebSocket client.
    persona           System prompts.
    memory_store      Persistent memory for the Companion daemon.

Apps live in ``picoh_ai.apps`` and are exposed as console_scripts.
"""

__version__ = "0.1.0"

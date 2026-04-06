from __future__ import annotations

import asyncio
import logging


LOGGER = logging.getLogger("example.compat")
_PYROGRAM_PATCHED = False


def ensure_event_loop() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def prepare_pyrogram_runtime() -> None:
    global _PYROGRAM_PATCHED

    ensure_event_loop()

    if _PYROGRAM_PATCHED:
        return

    import pyrogram.utils as pyrogram_utils

    def patched_get_peer_type(peer_id: int) -> str:
        if peer_id < 0:
            if pyrogram_utils.MIN_CHAT_ID <= peer_id:
                return "chat"

            if peer_id < pyrogram_utils.MAX_CHANNEL_ID:
                return "channel"
        elif 0 < peer_id <= pyrogram_utils.MAX_USER_ID:
            return "user"

        raise ValueError(f"Peer id invalid: {peer_id}")

    pyrogram_utils.MIN_CHANNEL_ID = -(10**16)
    pyrogram_utils.get_peer_type = patched_get_peer_type
    _PYROGRAM_PATCHED = True
    LOGGER.info("pyrogram_large_channel_id_patch_enabled")


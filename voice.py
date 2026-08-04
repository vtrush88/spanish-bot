from __future__ import annotations

import os
import sqlite3
import tempfile

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, Message

import db
from services import tts


async def send_card_voice(
    message: Message, conn: sqlite3.Connection, card, voice: str
) -> Message | None:
    """Send cached audio by file_id, else synthesize and cache the file_id.

    Sent as a voice message (Bot API ≥7.2 accepts MP3 in sendVoice): voice
    bubbles don't join the chat-wide music playlist, so playing one word
    never auto-plays the others. Cached file_ids are voice-type.
    Best-effort: on failure the text card is already shown, so we stay
    silent and return None. Returns the sent voice Message otherwise.
    """
    if card["audio_file_id"]:
        return await message.answer_voice(card["audio_file_id"])
    tmp = os.path.join(tempfile.gettempdir(), f"tts_{os.getpid()}_{card['id']}.mp3")
    try:
        await tts.synthesize(card["word"], voice, tmp)
        with open(tmp, "rb") as fh:
            sent = await message.answer_voice(
                BufferedInputFile(fh.read(), filename="произношение.mp3")
            )
        db.set_audio_file_id(conn, card["id"], sent.voice.file_id)
        return sent
    except (tts.TTSError, OSError, TelegramBadRequest):
        return None
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

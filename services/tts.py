from __future__ import annotations

import edge_tts

VOICE = "es-ES-ElviraNeural"


class TTSError(Exception):
    pass


async def synthesize(text: str, out_path: str) -> str:
    """Сгенерировать испанскую озвучку в ogg-файл. Возвращает путь."""
    try:
        comm = edge_tts.Communicate(text, VOICE)
        await comm.save(out_path)
    except Exception as exc:  # noqa: BLE001 - graceful degradation by design
        raise TTSError(str(exc)) from exc
    return out_path

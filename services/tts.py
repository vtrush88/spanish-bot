from __future__ import annotations

import edge_tts


class TTSError(Exception):
    pass


async def synthesize(text: str, voice: str, out_path: str) -> str:
    """Сгенерировать озвучку (mp3) голосом voice. Возвращает путь."""
    try:
        comm = edge_tts.Communicate(text, voice)
        await comm.save(out_path)
    except Exception as exc:  # noqa: BLE001 - graceful degradation by design
        raise TTSError(str(exc)) from exc
    return out_path

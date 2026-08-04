from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import tts


@pytest.mark.asyncio
async def test_synthesize_calls_edge_and_returns_path(tmp_path):
    out = tmp_path / "hola.ogg"
    fake_comm = MagicMock()
    fake_comm.save = AsyncMock()
    with patch("services.tts.edge_tts.Communicate", return_value=fake_comm) as ctor:
        result = await tts.synthesize("hola", "es-ES-XimenaNeural", str(out))
    ctor.assert_called_once_with("hola", "es-ES-XimenaNeural")
    fake_comm.save.assert_awaited_once_with(str(out))
    assert result == str(out)


@pytest.mark.asyncio
async def test_synthesize_wraps_errors():
    fake_comm = MagicMock()
    fake_comm.save = AsyncMock(side_effect=RuntimeError("network"))
    with patch("services.tts.edge_tts.Communicate", return_value=fake_comm):
        with pytest.raises(tts.TTSError):
            await tts.synthesize("hola", "es-ES-XimenaNeural", "/tmp/x.ogg")

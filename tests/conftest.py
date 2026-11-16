import pytest


@pytest.fixture(autouse=True)
def no_auto_update(monkeypatch):
    """Тесты никогда не скачивают программу с GitHub: иначе обновление перезапишет рабочие файлы."""
    from video_agents import updater

    monkeypatch.setattr(updater, "auto_update", lambda *args, **kwargs: [])

"""Изменение одной настройки config.yaml командой - без ручной правки файла."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from .config import load_settings


class ConfigEditError(ValueError):
    pass


def set_value(path: Path, key: str, raw_value: str):
    """Меняет настройку вида «раздел.поле» (например subtitles.show_scene_text) и возвращает новое значение.

    Значение разбирается как в YAML: true/false, числа, текст. Если с ним настройки становятся неверными,
    файл возвращается как был.
    """
    yaml = YAML()
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    data = yaml.load(original) if original.strip() else None
    if data is None:
        data = {}
    parts = [part for part in key.strip().split(".") if part]
    if not parts:
        raise ConfigEditError("Не указана настройка")
    value = YAML(typ="safe").load(raw_value) if raw_value.strip() else ""
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not hasattr(node, "setdefault"):
            raise ConfigEditError(f"«{part}» - это не раздел настроек")
    node[parts[-1]] = value
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh)
    try:
        settings = load_settings(path)
        current = settings
        for part in parts:
            current = getattr(current, part)
    except Exception as exc:
        path.write_text(original, encoding="utf-8")
        raise ConfigEditError(f"Такой настройки нет или значение не подходит: {key} = {raw_value}") from exc
    return current


def add_to_list(path: Path, key: str, item: str) -> list:
    """Добавляет элемент в список-настройку (например threads.exclude_topics) и возвращает новый список."""
    yaml = YAML()
    data = yaml.load(path.read_text(encoding="utf-8")) if path.exists() else None
    if data is None:
        data = {}
    *sections, field = key.split(".")
    node = data
    for section in sections:
        node = node.setdefault(section, {})
    items = node.get(field) or []
    if item.strip() and item.strip() not in items:
        items.append(item.strip())
    node[field] = items
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh)
    return list(items)


def set_list(path: Path, key: str, items: list[str]) -> list[str]:
    """Заменяет список-настройку целиком (например threads.priorities)."""
    yaml = YAML()
    data = yaml.load(path.read_text(encoding="utf-8")) if path.exists() else None
    if data is None:
        data = {}
    *sections, field = key.split(".")
    node = data
    for section in sections:
        node = node.setdefault(section, {})
    node[field] = [item.strip() for item in items if item.strip()]
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh)
    return list(node[field])


def apply_to(settings, key: str, value) -> None:
    """Применяет то же значение к уже загруженным настройкам (например, в работающем боте)."""
    *sections, field = key.strip().split(".")
    target = settings
    for section in sections:
        target = getattr(target, section)
    setattr(target, field, value)

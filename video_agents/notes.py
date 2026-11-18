"""Наброски автора: мысли и заготовки для роликов.

Пишутся в окне программы (workspace/notes.json) или текстовыми файлами .txt/.md в папке своих кадров.
Набросок, по которому уже сделан ролик, помечается и больше не предлагается.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

NOTE_EXT = {".txt", ".md"}


class Notes:
    def __init__(self, workspace: Path, folder: Path | None = None):
        self.file = Path(workspace) / "notes.json"
        self.folder = Path(folder) if folder else None
        self.lock = threading.RLock()

    def _load(self) -> dict:
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return {"notes": data.get("notes", []), "used_files": data.get("used_files", [])}

    def _save(self, data: dict) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.file)

    def add(self, text: str) -> dict:
        note = {"id": uuid.uuid4().hex[:8], "text": text.strip(), "created": time.strftime("%Y-%m-%d"), "used": False}
        with self.lock:
            data = self._load()
            data["notes"].append(note)
            self._save(data)
        return note

    def remove(self, note_id: str) -> None:
        with self.lock:
            data = self._load()
            data["notes"] = [n for n in data["notes"] if n["id"] != note_id]
            self._save(data)

    def mark_used(self, note_ids: list[str]) -> None:
        with self.lock:
            data = self._load()
            for note in data["notes"]:
                if note["id"] in note_ids:
                    note["used"] = True
            data["used_files"] += [i.removeprefix("file:") for i in note_ids if i.startswith("file:")]
            self._save(data)

    def all(self) -> list[dict]:
        """Наброски из окна и из текстовых файлов папки; у файловых id вида «file:путь»."""
        data = self._load()
        notes = list(data["notes"])
        if self.folder and self.folder.is_dir():
            for path in sorted(self.folder.rglob("*")):
                if path.is_file() and path.suffix.lower() in NOTE_EXT:
                    rel = path.relative_to(self.folder).as_posix()
                    try:
                        text = path.read_text(encoding="utf-8", errors="replace").strip()
                    except OSError:
                        continue
                    if text:
                        notes.append({"id": f"file:{rel}", "text": text[:3000], "created": "", "file": rel,
                                      "used": rel in data["used_files"]})
        return notes

    def fresh(self) -> list[dict]:
        return [note for note in self.all() if not note["used"]]

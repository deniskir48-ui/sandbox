"""Хранилище роликов: workspace/jobs/<id>/job.json + файлы рендера рядом."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from .models import Job, VideoIdea

_IDEAS = TypeAdapter(list[VideoIdea])


class JobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.jobs_dir = self.root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job: Job | str) -> Path:
        job_id = job if isinstance(job, str) else job.id
        return self.jobs_dir / job_id

    def save(self, job: Job) -> None:
        path = self.job_dir(job)
        path.mkdir(parents=True, exist_ok=True)
        tmp = path / "job.json.tmp"
        tmp.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path / "job.json")

    def load(self, job_id: str) -> Job:
        path = self.job_dir(job_id) / "job.json"
        if not path.exists():
            raise FileNotFoundError(f"Ролик {job_id} не найден в {self.jobs_dir}")
        return Job.model_validate_json(path.read_text(encoding="utf-8"))

    def all(self) -> list[Job]:
        return [
            Job.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(self.jobs_dir.glob("*/job.json"))
        ]

    def past_topics(self) -> list[str]:
        """Темы, которые уже сняты или ждут в очереди: их не нужно предлагать снова."""
        done = [job.idea.topic for job in self.all() if job.idea and job.status != "failed"]
        return done + [idea.topic for idea in self.queue()]

    # --- Очередь тем: выбранные идеи, которые снимаются в следующих запусках ---

    @property
    def queue_file(self) -> Path:
        return self.root / "ideas_queue.json"

    def queue(self) -> list[VideoIdea]:
        if not self.queue_file.exists():
            return []
        return _IDEAS.validate_json(self.queue_file.read_bytes())

    @property
    def ideas_log(self) -> Path:
        return self.root / "ideas_log.jsonl"

    def log_ideas(self, ideas: list[VideoIdea]) -> None:
        """Все придуманные агентом идеи, по строке на идею: ни одна хорошая тема не потеряется."""
        stamp = datetime.now().isoformat(timespec="seconds")
        with open(self.ideas_log, "a", encoding="utf-8") as fh:
            for idea in ideas:
                fh.write(f'{{"at": "{stamp}", "idea": {idea.model_dump_json()}}}\n')

    def save_queue(self, ideas: list[VideoIdea]) -> None:
        tmp = self.queue_file.with_suffix(".tmp")
        tmp.write_bytes(_IDEAS.dump_json(ideas, indent=2))
        tmp.replace(self.queue_file)

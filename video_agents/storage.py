"""Хранилище роликов: workspace/jobs/<id>/job.json + файлы рендера рядом."""

from __future__ import annotations

from pathlib import Path

from .models import Job


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
        return [job.idea.topic for job in self.all() if job.idea and job.status != "failed"]

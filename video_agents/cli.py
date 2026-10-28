"""Командная строка: python -m video_agents <команда>."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="video_agents", description="Агенты для создания и публикации коротких роликов")
    parser.add_argument("--config", default="config.yaml", help="путь к config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="полный цикл: идеи -> сценарий -> ролик -> (публикация)")
    run.add_argument("-n", "--count", type=int, default=1, help="сколько роликов сделать")
    run.add_argument("--topic", help="задать тему вручную вместо генерации идей")
    group = run.add_mutually_exclusive_group()
    group.add_argument("--publish", dest="publish", action="store_true", default=None, help="опубликовать сразу")
    group.add_argument("--no-publish", dest="publish", action="store_false", help="только смонтировать")

    ideas = sub.add_parser("ideas", help="только придумать идеи")
    ideas.add_argument("-n", "--count", type=int, default=5)

    publish = sub.add_parser("publish", help="опубликовать готовый ролик")
    publish.add_argument("job_id")
    publish.add_argument("--platform", action="append", choices=["youtube", "instagram", "tiktok"])

    render = sub.add_parser("render", help="пересобрать видео по сохранённому сценарию")
    render.add_argument("job_id")

    sub.add_parser("list", help="список роликов")
    sub.add_parser("update", help="обновить программу до последней версии с GitHub")

    auth = sub.add_parser("auth", help="однократная авторизация на платформе")
    auth.add_argument("platform", choices=["youtube", "tiktok"])

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("httpx", "googleapiclient", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    settings = load_settings(args.config)

    if args.command == "update":
        from pathlib import Path

        from .updater import update

        changed = update(Path(__file__).resolve().parent.parent)
        print(f"Обновлено файлов: {len(changed)}")
        for path in changed:
            print(f"    {path}")
        return 0

    if args.command == "auth":
        return _auth(args.platform, settings)

    from .pipeline import Pipeline

    pipeline = Pipeline(settings)

    if args.command == "run":
        jobs = pipeline.run(count=args.count, topic=args.topic, publish=args.publish)
        for job in jobs:
            _print_job(job)
        return 0 if all(job.status != "failed" for job in jobs) else 1

    if args.command == "ideas":
        for i, idea in enumerate(pipeline.ideas(args.count), 1):
            print(f"{i}. {idea.topic}\n   Угол: {idea.angle}\n   Хук: {idea.hook}\n")
        return 0

    if args.command == "publish":
        job = pipeline.publish(pipeline.store.load(args.job_id), args.platform)
        _print_job(job)
        return 0 if job.uploads and all(u.ok for u in job.uploads.values()) else 1

    if args.command == "render":
        job = pipeline.produce(pipeline.store.load(args.job_id))
        _print_job(job)
        return 0

    if args.command == "list":
        for job in pipeline.store.all():
            _print_job(job)
        return 0
    return 1


def _print_job(job) -> None:
    topic = job.idea.topic if job.idea else "-"
    print(f"[{job.status}] {job.id}  {topic}")
    if job.video_path:
        print(f"    видео: {job.video_path} ({job.duration or 0:.1f} с)")
    for upload in job.uploads.values():
        print(f"    {upload.platform}: {'OK ' + (upload.url or upload.id or '') if upload.ok else 'ОШИБКА ' + str(upload.error)}")
    if job.error:
        print(f"    ошибка: {job.error}")


def _auth(platform: str, settings) -> int:
    if platform == "youtube":
        from .publishers.youtube import authorize

        authorize(settings.secrets.youtube_client_secrets, settings.secrets.youtube_token_file)
        print(f"Готово, токен сохранён в {settings.secrets.youtube_token_file}")
        return 0

    from .publishers.tiktok import TikTokAuth

    auth = TikTokAuth(settings.secrets)
    print("1. Откройте ссылку и разрешите доступ:\n", auth.authorize_url())
    print("2. После редиректа скопируйте параметр code из адресной строки.")
    code = input("code: ").strip()
    auth.exchange_code(code)
    print(f"Готово, токен сохранён в {settings.secrets.tiktok_token_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

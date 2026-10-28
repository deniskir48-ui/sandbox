"""Командная строка: python -m video_agents <команда>."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_settings
from .models import manual_idea


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="video_agents", description="Агенты для создания и публикации коротких роликов")
    parser.add_argument("--config", default="config.yaml", help="путь к config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="полный цикл: идеи -> сценарий -> ролик -> (публикация)")
    run.add_argument("-n", "--count", type=int, default=1, help="сколько роликов сделать")
    run.add_argument("--topic", help="задать тему вручную вместо генерации идей")
    run.add_argument("--choose", action="store_true", help="показать 5 идей и выбрать, какую снимать")
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
    queue = sub.add_parser("queue", help="очередь тем: показать, добавить, убрать")
    queue.add_argument("action", nargs="?", choices=["add", "remove", "clear"],
                       help="add \"тема\" - добавить; remove 2 - убрать №2; clear - очистить")
    queue.add_argument("items", nargs="*", help="темы для add или номера для remove")
    sub.add_parser("update", help="обновить программу до последней версии с GitHub")

    auth = sub.add_parser("auth", help="однократная авторизация на платформе")
    auth.add_argument("platform", choices=["youtube", "instagram", "tiktok", "telegram"])

    sub.add_parser("bot", help="запустить Telegram-бота (управление с телефона)")

    schedule = sub.add_parser("schedule", help="запуск по расписанию (Планировщик задач Windows)")
    schedule.add_argument("action", choices=["add", "list", "remove"],
                          help="add 10:00 18:00 - каждый день в это время; list - показать; remove - убрать всё")
    schedule.add_argument("times", nargs="*", help="время запуска, например 10:00 18:30")
    schedule.add_argument("-n", "--count", type=int, default=1, help="сколько роликов за один запуск")

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

    if args.command == "schedule":
        return _schedule(args)

    if args.command == "bot":
        return _bot(settings)

    from .pipeline import Pipeline

    pipeline = Pipeline(settings)

    if args.command == "run":
        if args.choose:
            options = pipeline.ideas(5)
            _print_ideas(options)
            answer = input("Какие снимать? Номера через пробел (1 3 5), диапазон (2-4) или «все». "
                           "Enter - первая: ")
            chosen = [options[i] for i in parse_selection(answer, len(options))]
            pipeline.enqueue(chosen)
            later = max(len(chosen) - args.count, 0)
            print(f"\nВыбрано тем: {len(chosen)}. Сейчас делаю {len(chosen) - later}"
                  + (f", остальные {later} ждут в очереди и пойдут в следующие запуски." if later else ".") + "\n")
        jobs = pipeline.run(count=args.count, topic=args.topic, publish=args.publish)
        for job in jobs:
            _print_job(job)
        from .telegram.messages import notify_jobs

        notify_jobs(settings, jobs)  # если подключён Telegram - пришлём ролики туда
        return 0 if all(job.status != "failed" for job in jobs) else 1

    if args.command == "ideas":
        _print_ideas(pipeline.ideas(args.count))
        return 0

    if args.command == "publish":
        job = pipeline.publish(pipeline.store.load(args.job_id), args.platform)
        _print_job(job)
        return 0 if job.uploads and all(u.ok for u in job.uploads.values()) else 1

    if args.command == "render":
        job = pipeline.produce(pipeline.store.load(args.job_id))
        _print_job(job)
        return 0

    if args.command == "queue":
        if args.action == "add":
            pipeline.enqueue([manual_idea(text) for text in args.items if text.strip()])
        elif args.action == "remove":
            drop = {int(n) - 1 for n in args.items if n.isdigit()}
            pipeline.store.save_queue([idea for i, idea in enumerate(pipeline.store.queue()) if i not in drop])
        elif args.action == "clear":
            pipeline.store.save_queue([])
        queue = pipeline.store.queue()
        if not queue:
            print("Очередь пуста: при следующем запуске агент придумает новые темы.")
        _print_ideas(queue)
        return 0

    if args.command == "list":
        jobs = pipeline.store.all()
        for job in jobs:
            _print_job(job)
        paid = [job for job in jobs if job.cost_usd]
        if paid:
            total = sum(job.cost_usd for job in paid)
            print(f"\nРасходы на Claude: ${total:.2f} за {len(paid)} ролик(ов), в среднем ${total / len(paid):.2f}")
        return 0
    return 1


STAGE_NAMES = {"ideas": "идеи", "script": "сценарий", "critic": "редактор", "footage": "подбор видео",
               "metadata": "подписи"}


def parse_selection(answer: str, total: int) -> list[int]:
    """«1 3 5», «2-4», «1,2», «все» -> индексы с нуля; пустой ответ - первая идея."""
    answer = answer.strip().lower()
    if not answer:
        return [0]
    if answer in ("все", "всё", "all", "*"):
        return list(range(total))
    picked: list[int] = []
    for part in answer.replace(",", " ").split():
        start, _, end = part.partition("-")
        if not start.isdigit() or (end and not end.isdigit()):
            continue
        for number in range(int(start), int(end or start) + 1):
            if 1 <= number <= total and number - 1 not in picked:
                picked.append(number - 1)
    return picked or [0]


def _print_ideas(ideas) -> None:
    for i, idea in enumerate(ideas, 1):
        print(f"{i}. {idea.topic}  (узнаваемость {idea.relatability}/10)\n"
              f"   Проблема зрителя: {idea.viewer_problem}\n   Хук: {idea.hook}\n")


def _print_job(job) -> None:
    topic = job.idea.topic if job.idea else "-"
    print(f"[{job.status}] {job.id}  {topic}")
    if job.video_path:
        print(f"    видео: {job.video_path} ({job.duration or 0:.1f} с)")
    if job.cost_usd:
        parts = " · ".join(f"{STAGE_NAMES.get(stage, stage)} ${cost:.2f}" for stage, cost in job.cost_by_stage.items())
        print(f"    стоимость: ${job.cost_usd:.2f} ({parts})")
    for upload in job.uploads.values():
        print(f"    {upload.platform}: {'OK ' + (upload.url or upload.id or '') if upload.ok else 'ОШИБКА ' + str(upload.error)}")
    if job.error:
        print(f"    ошибка: {job.error}")


def _schedule(args) -> int:
    from . import scheduler

    try:
        if args.action == "add":
            if not args.times:
                print("Укажите время, например: python -m video_agents schedule add 10:00 18:00")
                return 1
            for name in scheduler.add(args.times, args.count):
                print(f"Создана задача «{name}»")
            print("Каждый запуск делает ролик (сначала из очереди тем) и публикует его. "
                  "Отчёт пишется в workspace\\schedule.log.\n"
                  "Компьютер в это время должен быть включён, а вы - вошли в Windows.")
        elif args.action == "list":
            tasks = scheduler.list_tasks()
            if not tasks:
                print("Расписание пустое.")
            for name, next_run in tasks:
                print(f"{name}: следующий запуск {next_run}")
        else:
            removed = scheduler.remove_all()
            print(f"Удалено задач: {len(removed)}")
    except scheduler.ScheduleError as exc:
        print(f"Ошибка: {exc}")
        return 1
    return 0


def _bot(settings) -> int:
    from pathlib import Path

    from .pipeline import Pipeline
    from .telegram.api import TelegramAccess, TelegramAPI
    from .telegram.bot import Bot

    access = TelegramAccess.load(settings.secrets)
    if not access:
        print("Бот не подключён. Выполните: python -m video_agents auth telegram")
        return 1
    log_file = Path(settings.workspace) / "bot.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    Bot(TelegramAPI(access.token), access.chat_id, Pipeline(settings)).run_forever()
    return 0


def _auth(platform: str, settings) -> int:
    if platform == "telegram":
        from .telegram import setup

        print("1. В Telegram откройте @BotFather, отправьте /newbot и придумайте имя боту.")
        print("2. BotFather пришлёт токен - длинную строку вида 123456:ABC-DEF...")
        token = input("Вставьте токен и нажмите Enter:\n").strip()
        setup.connect(token, settings.secrets)
        print("\nГотово! Бот привязан к вашему чату.")
        launcher = setup.install_autostart()
        if launcher:
            setup.start_now(launcher)
            print("Бот запущен в свёрнутом окне и будет запускаться сам при включении компьютера.\n"
                  "Окно «Video Agents bot» не закрывайте - его можно просто свернуть.")
        else:
            print("Запустите бота командой: python -m video_agents bot")
        return 0

    if platform == "youtube":
        from .publishers.youtube import authorize

        authorize(settings.secrets.youtube_client_secrets, settings.secrets.youtube_token_file)
        print(f"Готово, токен сохранён в {settings.secrets.youtube_token_file}")
        return 0

    if platform == "instagram":
        from .publishers.instagram import InstagramAuth

        token = input("Вставьте токен Instagram (длинная строка из кабинета разработчика) и нажмите Enter:\n").strip()
        data = InstagramAuth(settings.publish.instagram, settings.secrets).save(token)
        print(f"Готово! Подключён аккаунт @{data['username']}. Токен будет продлеваться автоматически.")
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

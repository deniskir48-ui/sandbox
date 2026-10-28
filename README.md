# Video Agents

Система агентов, которая сама придумывает темы, пишет и вычитывает сценарии, монтирует
вертикальные ролики и публикует их в **YouTube Shorts**, **Instagram Reels** и **TikTok**.

> 👉 Впервые запускаете? Откройте **[ИНСТРУКЦИЯ.md](ИНСТРУКЦИЯ.md)**: там всё по шагам, без программирования.
> Пример конфига уже настроен под англоязычный канал про спорт, питание и ЗОЖ.

```
 ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
 │ Агент идей   │──▶│ Сценарист    │◀─▶│ Редактор     │──▶│ SMM-агент    │
 │ (+веб-поиск) │   │              │   │ (до N правок)│   │ подписи/теги │
 └──────────────┘   └──────────────┘   └──────────────┘   └──────┬───────┘
                                                                 ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Производство: озвучка (edge-tts / ElevenLabs) → стоки Pixabay/Pexels → … │
 │ с подсветкой слов → музыка → ffmpeg → final.mp4 (1080×1920, H.264/AAC)   │
 └──────────────────────────────────────┬───────────────────────────────────┘
                                        ▼
               ┌────────────┬───────────────┬────────────┐
               │  YouTube   │   Instagram   │   TikTok   │
               └────────────┴───────────────┴────────────┘
```

| Агент | Что делает | Где |
|---|---|---|
| Агент идей | Ищет свежие инфоповоды (веб-поиск Claude), предлагает темы, не повторяя старые | `video_agents/agents/ideas.py` |
| Сценарист | Пишет сценарий по сценам: текст диктора, запрос для стоков, надпись на экране | `video_agents/agents/scriptwriter.py` |
| Редактор | Оценивает хук, удержание, факты, риски модерации; возвращает на доработку | `video_agents/agents/critic.py` |
| SMM-агент | Заголовки, описания, хэштеги под каждую платформу | `video_agents/agents/metadata.py` |
| Монтажёр | Смотрит превью найденных видео и выбирает то, что иллюстрирует слова диктора; если точного кадра нет — берёт кадр по общей теме или продолжает предыдущий, но не ставит случайное видео | `video_agents/agents/footage_editor.py` |
| Продюсер | Озвучка, подбор видео, субтитры, музыка, сборка | `video_agents/production/` |
| Публикаторы | Загрузка через официальные API платформ | `video_agents/publishers/` |

Оркестратор — `video_agents/pipeline.py`. Каждый ролик хранится в `workspace/jobs/<id>/`
(`job.json` со сценарием, оценками редактора и ссылками на публикации + все файлы монтажа).

## Быстрый старт

Нужны Python 3.11+ и ffmpeg (`brew install ffmpeg` / `sudo apt install ffmpeg`).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # опишите нишу, аудиторию, тон
cp .env.example .env                 # минимум: ANTHROPIC_API_KEY и PIXABAY_API_KEY (или PEXELS_API_KEY)

python -m video_agents ideas -n 5                 # посмотреть, что предлагает агент идей
python -m video_agents run                        # сделать 1 ролик (без публикации)
python -m video_agents run --topic "Почему небо голубое"
python -m video_agents list                       # все ролики и их статусы
python -m video_agents publish <id>               # опубликовать проверенный ролик
python -m video_agents publish <id> --platform youtube
python -m video_agents render <id>                # пересобрать видео после ручной правки job.json
python -m video_agents update                     # обновить программу до последней версии с GitHub
```

По умолчанию `auto_publish: false`: агенты делают ролик, вы смотрите `final.mp4` и запускаете
`publish`. Когда качество устроит — включите `auto_publish: true` или запускайте `run --publish`.

## Подключение платформ

### YouTube
1. [Google Cloud Console](https://console.cloud.google.com/) → создайте проект → включите **YouTube Data API v3**.
2. OAuth consent screen → добавьте свой Google-аккаунт в тестовые пользователи.
3. Credentials → OAuth client ID → тип **Desktop app** → скачайте JSON в `secrets/youtube_client_secret.json`.
4. `python -m video_agents auth youtube` — откроется браузер, токен сохранится в `secrets/youtube_token.json`.

Квота API по умолчанию — 10 000 единиц в сутки, а загрузка видео — одна из самых дорогих операций,
поэтому без увеличения квоты получится лишь несколько роликов в день.
Пока приложение не прошло проверку Google, загруженные ролики могут блокироваться как private.

### Instagram
1. Аккаунт Instagram должен быть **профессиональным** (Business или Creator).
2. [Meta for Developers](https://developers.facebook.com/) → приложение → продукт **Instagram** →
   «API setup with Instagram login» → сгенерируйте токен с правами `instagram_business_basic`,
   `instagram_business_content_publish`.
3. В `.env`: `INSTAGRAM_ACCESS_TOKEN` (долгоживущий, 60 дней — продлевайте) и `INSTAGRAM_USER_ID`.

Если вы подключаете Instagram через Facebook-страницу, поставьте `graph_host: graph.facebook.com`.
Лимит API — около 50 публикаций в сутки.

### TikTok
1. [TikTok for Developers](https://developers.tiktok.com/) → приложение → продукты **Login Kit** и
   **Content Posting API** (включите Direct Post), scopes `video.publish`, `video.upload`.
2. Укажите Redirect URI (любой ваш https-адрес) и заполните `TIKTOK_*` в `.env`.
3. `python -m video_agents auth tiktok` — откройте ссылку, разрешите доступ, вставьте `code` из адреса.

Важно: до прохождения аудита TikTok публикует видео от непроверенных приложений **только приватно**
(`SELF_ONLY`) — система делает это автоматически. Альтернатива — `mode: inbox`: ролик попадёт
в черновики приложения TikTok, и вы опубликуете его в один тап (там же можно добавить трендовый звук).

## Запуск по расписанию

Cron (2 ролика в 10:00 и 18:00):
```cron
0 10,18 * * * cd /path/to/sandbox && .venv/bin/python -m video_agents run --publish >> workspace/cron.log 2>&1
```

## Настройка качества

- **Ниша и стиль** — `channel` в `config.yaml`; `extra_rules` попадают во все агенты,
  `disclaimer` дописывается в описания (для тем о здоровье: «not medical advice»).
- **Промпты агентов** — константы `SYSTEM` в `video_agents/agents/*.py`.
- **Строгость редактора** — `llm.min_score` и `llm.max_revisions`.
- **Длина ролика** — `channel.video_length_seconds` (обычная, 10 с) и `channel.max_video_length_seconds`
  (потолок для сильных роликов, 20 с). Сценарист считает по 2.5 слова в секунду, а сценарий длиннее потолка
  автоматически сокращается.
- **Подбор видео** — `footage.ai_selection` (монтажёр смотрит превью, ~несколько центов за ролик)
  и `footage.candidates` (сколько вариантов показывать на каждый запрос).
- **Голос** — `edge` бесплатен (en-US-AndrewMultilingualNeural, en-US-AvaMultilingualNeural, ru-RU-SvetlanaNeural и др.); `elevenlabs` звучит
  заметно живее, в `voice.voice` укажите voice_id.
- **Шрифт субтитров** — положите `.ttf` в `assets/fonts/` и укажите имя в `subtitles.font`
  (хорошо смотрятся Montserrat ExtraBold, Inter Black).
- **Музыка** — файлы в `assets/music/`; только треки с лицензией (например, YouTube Audio Library),
  иначе платформы заглушат звук или заблокируют ролик.

## Правила платформ

- Ролики помечаются как созданные с помощью ИИ (`ai_disclosure`) — этого требуют YouTube и TikTok
  для синтетического контента.
- Массовая публикация однотипного контента без ценности (spam / reused content) ведёт к
  демонетизации и пессимизации. Редактор отсекает слабые сценарии, но выборочно смотрите ролики сами.
- Стоки Pixabay и Pexels бесплатны для коммерческого использования, атрибуция не обязательна.

## Тесты

```bash
pytest
```
Тесты прогоняют весь конвейер с фейковыми LLM/озвучкой/публикаторами и настоящим ffmpeg-рендером.

"""Субтитры в стиле Shorts/Reels: крупные слова по центру с подсветкой текущего слова."""

from __future__ import annotations

import re

from .tts import Word


def hex_to_ass(color: str) -> str:
    """#RRGGBB -> &H00BBGGRR (формат цвета ASS)."""
    color = color.lstrip("#")
    r, g, b = color[0:2], color[2:4], color[4:6]
    return f"&H00{b}{g}{r}".upper()


def ass_time(seconds: float) -> str:
    centis = max(0, round(seconds * 100))
    h, rem = divmod(centis, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def clean_word(text: str) -> str:
    return re.sub(r"[{}\\]", "", text).strip()


def group_words(words: list[Word], max_words: int, max_gap: float = 0.6) -> list[list[Word]]:
    """Режем поток слов на короткие фразы: по количеству слов, паузам и концу предложения."""
    groups: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current and (len(current) >= max_words or word.start - current[-1].end > max_gap):
            groups.append(current)
            current = []
        current.append(word)
        if word.text.rstrip().endswith((".", "!", "?", "…")):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def build_ass(
    words: list[Word],
    cfg,
    width: int,
    height: int,
    captions: list[tuple[float, float, str]] = (),
) -> str:
    """captions - надписи сцен вверху кадра: (начало, конец, текст)."""
    primary = hex_to_ass(cfg.color)
    highlight = hex_to_ass(cfg.highlight_color)
    outline = hex_to_ass(cfg.outline_color)
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Main,{cfg.font},{cfg.font_size},{primary},{primary},{outline},&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,{cfg.outline},2,2,80,80,{cfg.margin_v},1\n"
        f"Style: Caption,{cfg.font},{int(cfg.font_size * 0.7)},{primary},{primary},{outline},&H80000000,"
        f"-1,0,0,0,100,100,0,0,3,{cfg.outline},0,8,80,80,260,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events: list[str] = [
        f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{clean_word(text)}"
        for start, end, text in captions
    ]
    groups = group_words(words, cfg.max_words)
    for index, group in enumerate(groups):
        tokens = [clean_word(w.text) for w in group]
        if cfg.uppercase:
            tokens = [t.upper() for t in tokens]
        next_start = groups[index + 1][0].start if index + 1 < len(groups) else group[-1].end + 0.3
        group_end = min(group[-1].end + 0.3, next_start)
        # Одна строка на каждое слово группы: то же самое, но текущее слово подсвечено.
        for i, word in enumerate(group):
            start = word.start
            end = group[i + 1].start if i + 1 < len(group) else group_end
            if end <= start:
                continue
            text = " ".join(
                f"{{\\c{highlight}}}{t}{{\\c{primary}}}" if j == i else t for j, t in enumerate(tokens)
            )
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Main,,0,0,0,,{text}")
    return header + "\n".join(events) + "\n"

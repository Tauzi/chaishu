from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


MAX_CHARS = 12000


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_ROOT = app_root()
DATA_DIR = APP_ROOT / "data"
BOOKS_DIR = DATA_DIR / "books"
CONFIG_PATH = DATA_DIR / "config.json"
STATE_PATH = DATA_DIR / "state.json"

CHAPTER_NUMBER = r"第[一二三四五六七八九十百千万零〇两\d]+"
CHAPTER_RE = re.compile(
    rf"(?m)^\s*({CHAPTER_NUMBER}(?:[章回][^\n\r]{{0,60}}|[集部卷][\s：:、.．【（(《-][^\n\r]{{0,60}}|节(?:\s|[：:、.．【（(《-])[^\n\r]{{0,60}}))\s*$"
)


@dataclass
class Chapter:
    title: str
    text: str
    outline: str = ""


@dataclass
class BookProject:
    name: str
    book_dir: Path
    source_path: Path
    output_dir: Path
    characters_path: Path
    chapters: list[Chapter]


def safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned[:80] or fallback).rstrip(" .")


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def split_by_chapter(text: str) -> list[Chapter]:
    matches = list(CHAPTER_RE.finditer(text))
    if not matches:
        return [Chapter("全文", text.strip())]
    chapters: list[Chapter] = []
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            chapters.extend(split_by_size(title, body, MAX_CHARS))
    return chapters


def split_by_size(title: str, text: str, max_chars: int) -> list[Chapter]:
    if len(text) <= max_chars:
        return [Chapter(title, text)]
    chunks: list[Chapter] = []
    start = 0
    part = 1
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            break_at = max(text.rfind("\n", start, end), text.rfind("。", start, end))
            if break_at > start + max_chars // 2:
                end = break_at + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(Chapter(f"{title}_part{part:02d}", chunk))
            part += 1
        start = end
    return chunks


def load_config() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(api_key: str, base_url: str, model: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps({"api_key": api_key, "base_url": base_url, "model": model}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(
    book_dir: Path | None,
    selected_index: int | None = None,
    geometry: str | None = None,
    sash_positions: list[int] | None = None,
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state: dict[str, object] = load_state()
    if book_dir is not None:
        state["last_book_dir"] = str(book_dir)
    if selected_index is not None:
        state["selected_index"] = selected_index
    if geometry is not None:
        state["geometry"] = geometry
    if sash_positions is not None:
        state["sash_positions"] = sash_positions
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def unique_dir(parent: Path, name: str) -> Path:
    path = parent / name
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = parent / f"{name}_{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def outline_filename(index: int, chapter: Chapter) -> str:
    return f"{index:04d}_{safe_name(chapter.title, 'chapter')}_拆书细纲.md"


def main_content_collection_path(project: BookProject) -> Path:
    return project.output_dir / f"{safe_name(project.name, 'book')}_剧情主要内容合集.md"


def extract_main_content(outline: str) -> str:
    lines = outline.splitlines()
    collecting = False
    content: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.fullmatch(r"##\s*剧情主要内容\s*", stripped):
            collecting = True
            content = []
            continue
        if collecting and re.match(r"##\s+", stripped):
            break
        if collecting:
            content.append(line.rstrip())
    return "\n".join(content).strip()


def write_main_content_collection(project: BookProject) -> Path:
    parts = [f"# {project.name} 剧情主要内容合集"]
    for index, chapter in enumerate(project.chapters, start=1):
        if not chapter.outline:
            continue
        main_content = extract_main_content(chapter.outline)
        if not main_content:
            continue
        parts.append(f"## {index}. {chapter.title}\n\n{main_content}")
    path = main_content_collection_path(project)
    path.write_text("\n\n".join(parts).strip() + "\n", encoding="utf-8")
    return path


def empty_character_registry() -> dict:
    return {
        "main_character": {
            "name": "",
            "aliases": [],
            "identity": "",
            "personality": [],
            "abilities_resources": [],
            "goals": [],
            "status": "",
            "relationships": [],
            "appearances": [],
        },
        "characters": [],
    }


def import_book(original_path: Path) -> BookProject:
    book_name = safe_name(original_path.stem, "未命名书籍")
    book_dir = unique_dir(BOOKS_DIR, book_name)
    book_dir.mkdir(parents=True, exist_ok=True)
    source_path = book_dir / original_path.name
    shutil.copy2(original_path, source_path)
    project = load_book(book_dir)
    save_character_registry(project.characters_path, empty_character_registry())
    return project


def list_books() -> list[Path]:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted([path for path in BOOKS_DIR.iterdir() if path.is_dir()], key=lambda p: p.name.lower())


def load_book(book_dir: Path) -> BookProject:
    txt_files = sorted(book_dir.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"书籍目录中没有 TXT：{book_dir}")
    source_path = txt_files[0]
    name = safe_name(source_path.stem, "未命名书籍")
    output_dir = book_dir / f"{name}拆书细纲"
    output_dir.mkdir(parents=True, exist_ok=True)
    chapters = split_by_chapter(read_text(source_path))
    for index, chapter in enumerate(chapters, start=1):
        outline_path = output_dir / outline_filename(index, chapter)
        if outline_path.exists():
            chapter.outline = outline_path.read_text(encoding="utf-8", errors="ignore")
    return BookProject(name, book_dir, source_path, output_dir, book_dir / "characters.json", chapters)


def load_character_registry(path: Path | None) -> dict:
    if path is None or not path.exists():
        return empty_character_registry()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_character_registry()


def save_character_registry(path: Path | None, registry: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


def build_outline_context(chapters: list[Chapter], current_index: int, registry: dict, recent_count: int = 2) -> str:
    parts: list[str] = []
    main = registry.get("main_character") or {}
    if any(main.get(key) for key in ("name", "identity", "status")):
        parts.append("【主角档案】")
        parts.append(json.dumps(main, ensure_ascii=False, indent=2))
    start = max(0, current_index - recent_count)
    previous = []
    for index in range(start, current_index):
        if chapters[index].outline:
            previous.append(f"【前文第{index + 1}章：{chapters[index].title}】\n{chapters[index].outline}")
    if previous:
        parts.append("【最近章节细纲】")
        parts.extend(previous)
    return "\n\n".join(parts)[:16000]

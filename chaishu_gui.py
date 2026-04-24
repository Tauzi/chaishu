from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path

if getattr(sys, "frozen", False):
    bundle_dir = getattr(sys, "_MEIPASS", "")
    if bundle_dir and bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)
    os.environ.setdefault("TCL_LIBRARY", os.path.join(bundle_dir, "tcl", "tcl8.6"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(bundle_dir, "tcl", "tk8.6"))

from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, IntVar, StringVar, Tk, filedialog, messagebox
from tkinter import font as tkfont
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from api import DEFAULT_BASE_URL, DEFAULT_MODEL, call_outline, fetch_models, update_character_registry
from storage import (
    DATA_DIR,
    BookProject,
    build_outline_context,
    empty_character_registry,
    import_book,
    list_books,
    load_book,
    load_character_registry,
    load_config,
    load_state,
    outline_filename,
    save_character_registry,
    save_config,
    save_state,
)


APP_TITLE = "拆书细纲生成器-问题反馈QQ1223156656"


def format_list(values: list) -> str:
    return "、".join(str(value) for value in values if str(value).strip())


def tree_text(label: str, value: object) -> str:
    if isinstance(value, list):
        value_text = format_list(value) or "暂无"
    else:
        value_text = str(value).strip() if value else "暂无"
    return f"{label}：{value_text}"


def normalize_outline_text(text: str) -> str:
    lines = text.splitlines()
    normalized: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip() == "-":
            index += 1
            while index < len(lines) and not lines[index].strip():
                index += 1
            if index < len(lines):
                next_line = lines[index].strip()
                if next_line:
                    normalized.append(f"- {next_line.lstrip('-').strip()}")
                    index += 1
                    continue
            continue
        if normalized and line.startswith((" ", "\t")) and normalized[-1].lstrip().startswith("- "):
            normalized[-1] = f"{normalized[-1].rstrip()} {line.strip()}"
        else:
            normalized.append(line)
        index += 1
    return "\n".join(normalized)


class ChaishuApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.minsize(1180, 760)
        self.apply_initial_geometry()

        config = load_config()
        self.api_key = StringVar(value=config.get("api_key") or os.environ.get("OPENAI_API_KEY", ""))
        self.base_url = StringVar(value=config.get("base_url") or os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL))
        self.model = StringVar(value=config.get("model") or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL))
        self.only_empty = BooleanVar(value=True)
        self.status = StringVar(value="导入 TXT 后开始拆书。")
        self.book_choice = StringVar(value="")
        self.character_search = StringVar(value="")
        self.editor_font_size = IntVar(value=13)
        self.editor_status = StringVar(value="未选择章节")

        self.project: BookProject | None = None
        self.character_registry = empty_character_registry()
        self.book_dirs: list[Path] = []
        self.character_items: dict[str, dict] = {}
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.current_chapter_index: int | None = None
        self.running = False
        self.paused = False
        self.pause_event = threading.Event()
        self.pause_event.set()

        self.build_ui()
        self.root.after(120, self.restore_layout)
        self.refresh_book_choices()
        self.restore_last_session()
        self.root.after(200, self.poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def apply_initial_geometry(self) -> None:
        state = load_state()
        geometry = state.get("geometry")
        if isinstance(geometry, str) and re.match(r"^\d+x\d+[+-]\d+[+-]\d+$", geometry):
            self.root.geometry(geometry)
            return
        width = 1500
        height = 900
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=X)
        ttk.Button(top, text="导入TXT", command=self.import_txt).pack(side=LEFT)
        ttk.Button(top, text="打开数据目录", command=self.open_data_dir).pack(side=LEFT, padx=6)
        ttk.Label(top, text="书库").pack(side=LEFT, padx=(8, 2))
        self.book_box = ttk.Combobox(top, textvariable=self.book_choice, width=28, state="readonly")
        self.book_box.pack(side=LEFT)
        self.book_box.bind("<<ComboboxSelected>>", self.switch_book)
        self.start_button = ttk.Button(top, text="开始拆书", command=self.start)
        self.start_button.pack(side=LEFT, padx=(8, 0))
        self.pause_button = ttk.Button(top, text="暂停", command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side=LEFT, padx=6)
        ttk.Button(top, text="保存配置", command=self.save_current_config).pack(side=LEFT)
        ttk.Checkbutton(top, text="跳过已有结果", variable=self.only_empty).pack(side=LEFT, padx=8)

        config = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        config.pack(fill=X)
        ttk.Label(config, text="API Key").pack(side=LEFT)
        ttk.Entry(config, textvariable=self.api_key, show="*", width=27).pack(side=LEFT, padx=4)
        ttk.Label(config, text="接口地址").pack(side=LEFT)
        ttk.Entry(config, textvariable=self.base_url, width=42).pack(side=LEFT, padx=4)
        ttk.Label(config, text="模型").pack(side=LEFT)
        self.model_box = ttk.Combobox(config, textvariable=self.model, width=24)
        self.model_box.pack(side=LEFT, padx=4)
        ttk.Button(config, text="获取模型", command=self.start_fetch_models).pack(side=LEFT)

        self.main_pane = ttk.PanedWindow(self.root, orient="horizontal")
        self.main_pane.pack(fill=BOTH, expand=True, padx=10, pady=8)

        left = ttk.Frame(self.main_pane)
        self.main_pane.add(left, weight=1)
        left.configure(width=300)
        self.chapter_list = ttk.Treeview(left, columns=("title", "status"), show="headings", height=24)
        self.chapter_list.heading("title", text="章节")
        self.chapter_list.heading("status", text="状态")
        self.chapter_list.column("title", width=320)
        self.chapter_list.column("status", width=90, anchor="center")
        self.chapter_list.pack(fill=BOTH, expand=True)
        self.chapter_list.bind("<<TreeviewSelect>>", self.show_selected)

        center = ttk.Frame(self.main_pane)
        self.main_pane.add(center, weight=4)
        center.configure(width=760)
        editor_bar = ttk.Frame(center)
        editor_bar.pack(fill=X, pady=(0, 4))
        ttk.Label(editor_bar, text="细纲编辑器").pack(side=LEFT)
        ttk.Button(editor_bar, text="A-", width=4, command=self.decrease_editor_font).pack(side=LEFT, padx=(8, 2))
        ttk.Label(editor_bar, textvariable=self.editor_font_size, width=3, anchor="center").pack(side=LEFT)
        ttk.Button(editor_bar, text="A+", width=4, command=self.increase_editor_font).pack(side=LEFT, padx=2)
        ttk.Button(editor_bar, text="保存当前细纲", command=self.save_current_outline).pack(side=LEFT, padx=(8, 2))
        ttk.Button(editor_bar, text="重新高亮", command=self.highlight_editor).pack(side=LEFT, padx=2)
        ttk.Label(editor_bar, textvariable=self.editor_status).pack(side=RIGHT)

        self.editor_font = tkfont.Font(family="Microsoft YaHei UI", size=self.editor_font_size.get())
        self.viewer = ScrolledText(
            center,
            wrap="char",
            font=self.editor_font,
            undo=True,
            maxundo=80,
            spacing1=0,
            spacing2=0,
            spacing3=3,
            padx=10,
            pady=8,
        )
        self.viewer.pack(fill=BOTH, expand=True)
        self.viewer.bind("<<Modified>>", self.on_editor_modified)
        self.configure_editor_tags()

        right = ttk.Frame(self.main_pane)
        self.main_pane.add(right, weight=1)
        right.configure(width=320)
        ttk.Label(right, text="角色", anchor="center").pack(fill=X)
        search_entry = ttk.Entry(right, textvariable=self.character_search)
        search_entry.pack(fill=X, padx=4, pady=(2, 6))
        self.character_search.trace_add("write", lambda *_args: self.refresh_character_view())
        self.character_tree = ttk.Treeview(right, show="tree", height=14)
        self.character_tree.pack(fill=BOTH, expand=True)
        self.character_tree.bind("<<TreeviewSelect>>", self.show_character_detail)
        ttk.Label(right, text="详情", anchor="center").pack(fill=X, pady=(6, 0))
        self.character_detail = ScrolledText(right, wrap="word", height=16, font=("Microsoft YaHei UI", 10))
        self.character_detail.pack(fill=BOTH, expand=True)

        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill=X)
        ttk.Label(bottom, textvariable=self.status).pack(side=LEFT)

    def refresh_book_choices(self) -> None:
        self.book_dirs = list_books()
        self.book_box.configure(values=[path.name for path in self.book_dirs])

    def import_txt(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("TXT 文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self.project = import_book(Path(path))
            self.character_registry = load_character_registry(self.project.characters_path)
            self.refresh_book_choices()
            self.book_choice.set(self.project.book_dir.name)
            self.refresh_all_views()
            save_state(self.project.book_dir)
            self.status.set(f"已导入 {len(self.project.chapters)} 个章节/分块，数据已保存到：{self.project.book_dir}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, str(exc))

    def switch_book(self, _event: object | None = None) -> None:
        name = self.book_choice.get()
        for book_dir in self.book_dirs:
            if book_dir.name == name:
                self.load_project(book_dir)
                return

    def load_project(self, book_dir: Path, selected_index: int = 0) -> None:
        try:
            self.project = load_book(book_dir)
            self.character_registry = load_character_registry(self.project.characters_path)
            self.book_choice.set(self.project.book_dir.name)
            self.refresh_all_views(selected_index)
            save_state(self.project.book_dir, selected_index)
            self.status.set(f"已切换书籍：{self.project.name}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, str(exc))

    def restore_last_session(self) -> None:
        state = load_state()
        book_dir_value = state.get("last_book_dir")
        if not book_dir_value:
            return
        book_dir = Path(book_dir_value)
        if not book_dir.exists():
            return
        self.load_project(book_dir, int(state.get("selected_index", 0) or 0))

    def refresh_all_views(self, selected_index: int = 0) -> None:
        self.refresh_list()
        self.refresh_character_view()
        if self.project and self.project.chapters:
            selected_index = max(0, min(selected_index, len(self.project.chapters) - 1))
            item = str(selected_index)
            self.chapter_list.selection_set(item)
            self.chapter_list.see(item)
            self.show_selected()

    def open_data_dir(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(DATA_DIR)

    def restore_layout(self) -> None:
        state = load_state()
        positions = state.get("sash_positions")
        if not isinstance(positions, list):
            self.set_default_sashes()
            return
        try:
            for index, position in enumerate(positions):
                self.main_pane.sashpos(index, int(position))
        except Exception:
            self.set_default_sashes()

    def set_default_sashes(self) -> None:
        self.root.update_idletasks()
        width = max(1180, self.main_pane.winfo_width())
        try:
            self.main_pane.sashpos(0, int(width * 0.22))
            self.main_pane.sashpos(1, int(width * 0.78))
        except Exception:
            return

    def current_sash_positions(self) -> list[int]:
        try:
            return [self.main_pane.sashpos(0), self.main_pane.sashpos(1)]
        except Exception:
            return []

    def refresh_list(self) -> None:
        self.chapter_list.delete(*self.chapter_list.get_children())
        if not self.project:
            return
        for index, chapter in enumerate(self.project.chapters):
            status = "已完成" if chapter.outline else "待处理"
            self.chapter_list.insert("", END, iid=str(index), values=(chapter.title, status))

    def show_selected(self, _event: object | None = None) -> None:
        if not self.project:
            return
        selected = self.chapter_list.selection()
        if not selected:
            return
        index = int(selected[0])
        self.current_chapter_index = index
        save_state(self.project.book_dir, index)
        chapter = self.project.chapters[index]
        self.viewer.delete("1.0", END)
        self.viewer.insert(END, normalize_outline_text(chapter.outline or chapter.text))
        self.viewer.edit_modified(False)
        self.editor_status.set("已生成细纲" if chapter.outline else "显示原文，生成后可编辑")
        self.highlight_editor()

    def configure_editor_tags(self) -> None:
        self.viewer.tag_configure("h1", font=("Microsoft YaHei UI", self.editor_font_size.get() + 6, "bold"), foreground="#0f4c81", spacing1=8, spacing3=6)
        self.viewer.tag_configure("h2", font=("Microsoft YaHei UI", self.editor_font_size.get() + 3, "bold"), foreground="#1769aa", spacing1=6, spacing3=4)
        self.viewer.tag_configure("bullet", lmargin1=8, lmargin2=30, spacing1=0, spacing2=0, spacing3=2, foreground="#243b53")
        self.viewer.tag_configure("label", font=("Microsoft YaHei UI", self.editor_font_size.get(), "bold"), foreground="#8a4b08")

    def highlight_editor(self) -> None:
        for tag in ("h1", "h2", "bullet", "label"):
            self.viewer.tag_remove(tag, "1.0", END)
        content = self.viewer.get("1.0", END)
        for line_number, line in enumerate(content.splitlines(), start=1):
            start = f"{line_number}.0"
            end = f"{line_number}.end"
            if line.startswith("# "):
                self.viewer.tag_add("h1", start, end)
            elif line.startswith("## "):
                self.viewer.tag_add("h2", start, end)
            elif line.lstrip().startswith("- "):
                self.viewer.tag_add("bullet", start, end)
            for match in re.finditer(r"`[^`]+`|剧情主要内容|细节剧情点|情节分析|爽点分析|节奏控制|钩子设计|读者看点", line):
                self.viewer.tag_add("label", f"{line_number}.{match.start()}", f"{line_number}.{match.end()}")

    def increase_editor_font(self) -> None:
        self.editor_font_size.set(min(28, self.editor_font_size.get() + 1))
        self.apply_editor_font()

    def decrease_editor_font(self) -> None:
        self.editor_font_size.set(max(9, self.editor_font_size.get() - 1))
        self.apply_editor_font()

    def apply_editor_font(self) -> None:
        self.editor_font.configure(size=self.editor_font_size.get())
        self.configure_editor_tags()
        self.highlight_editor()

    def on_editor_modified(self, _event: object | None = None) -> None:
        if self.viewer.edit_modified():
            if self.current_chapter_index is not None:
                self.editor_status.set("未保存")

    def save_current_outline(self) -> None:
        if not self.project or self.current_chapter_index is None:
            messagebox.showwarning(APP_TITLE, "请先选择一个章节。")
            return
        chapter = self.project.chapters[self.current_chapter_index]
        content = normalize_outline_text(self.viewer.get("1.0", "end-1c")).strip()
        if not content:
            messagebox.showwarning(APP_TITLE, "当前编辑器内容为空，未保存。")
            return
        chapter.outline = content
        output_path = self.project.output_dir / outline_filename(self.current_chapter_index + 1, chapter)
        output_path.write_text(content, encoding="utf-8")
        self.chapter_list.set(str(self.current_chapter_index), "status", "已完成")
        self.viewer.edit_modified(False)
        self.editor_status.set("已保存")
        self.highlight_editor()

    def refresh_character_view(self) -> None:
        self.character_tree.delete(*self.character_tree.get_children())
        self.character_items = {}
        registry = self.character_registry or empty_character_registry()
        main = registry.get("main_character") or {}
        characters = registry.get("characters") or []
        keyword = self.character_search.get().strip().lower()
        if not any(main.get(key) for key in ("name", "identity", "status")) and not characters:
            self.character_tree.insert("", END, text="暂无角色信息")
            self.show_character_text("暂无角色信息。")
            return
        main_name = main.get("name") or "主角"
        if self.character_matches(main_name, main, keyword):
            main_id = self.character_tree.insert("", END, text=f"★ {main_name}", open=True)
            self.character_items[main_id] = {"type": "main", "data": main}
        relationships = main.get("relationships") or []
        if relationships:
            relation_root = self.character_tree.insert("", END, text="主角关系", open=True)
            for item in relationships:
                name = item.get("name") or "未知角色"
                relation = item.get("relation") or "关系未知"
                if self.character_matches(name, item, keyword):
                    relation_id = self.character_tree.insert(relation_root, END, text=f"{name}｜{relation}")
                    self.character_items[relation_id] = {"type": "relationship", "data": item}
            if not self.character_tree.get_children(relation_root):
                self.character_tree.delete(relation_root)
        if characters:
            others_root = self.character_tree.insert("", END, text=f"其他角色（{len(characters)}）", open=True)
            for item in characters:
                name = item.get("name") or "未知角色"
                relation = item.get("relationship_to_protagonist") or "与主角关系未知"
                if self.character_matches(name, item, keyword):
                    character_id = self.character_tree.insert(others_root, END, text=f"{name}｜{relation}")
                    self.character_items[character_id] = {"type": "character", "data": item}
            if not self.character_tree.get_children(others_root):
                self.character_tree.delete(others_root)
        first = self.first_character_item()
        if first:
            self.character_tree.selection_set(first)
            self.show_character_detail()
        else:
            self.show_character_text("没有匹配的角色。")

    def character_matches(self, name: str, data: dict, keyword: str) -> bool:
        if not keyword:
            return True
        return keyword in json.dumps({"name": name, **data}, ensure_ascii=False).lower()

    def first_character_item(self) -> str | None:
        for item in self.character_tree.get_children(""):
            if item in self.character_items:
                return item
            children = self.character_tree.get_children(item)
            if children:
                return children[0]
        return None

    def show_character_text(self, text: str) -> None:
        self.character_detail.delete("1.0", END)
        self.character_detail.insert(END, text)

    def show_character_detail(self, _event: object | None = None) -> None:
        selected = self.character_tree.selection()
        if not selected:
            return
        item = self.character_items.get(selected[0])
        if not item:
            return
        data = item["data"]
        if item["type"] == "main":
            text = self.main_character_detail(data)
        elif item["type"] == "relationship":
            text = self.relationship_detail(data)
        else:
            text = self.other_character_detail(data)
        self.show_character_text(text)

    def main_character_detail(self, data: dict) -> str:
        return "\n\n".join([
            data.get("name") or "主角",
            tree_text("别名", data.get("aliases") or []),
            tree_text("身份", data.get("identity")),
            tree_text("性格", data.get("personality") or []),
            tree_text("能力/资源", data.get("abilities_resources") or []),
            tree_text("目标", data.get("goals") or []),
            tree_text("最新状态", data.get("status")),
        ])

    def relationship_detail(self, data: dict) -> str:
        return "\n\n".join([
            f"{data.get('name') or '未知角色'}｜{data.get('relation') or '关系未知'}",
            tree_text("关系细节", data.get("details")),
            tree_text("双方态度", data.get("attitude")),
            tree_text("最近更新", data.get("chapter")),
        ])

    def other_character_detail(self, data: dict) -> str:
        return "\n\n".join([
            data.get("name") or "未知角色",
            tree_text("别名", data.get("aliases") or []),
            tree_text("身份", data.get("identity")),
            tree_text("剧情功能", data.get("role")),
            tree_text("与主角关系", data.get("relationship_to_protagonist")),
            tree_text("最新状态", data.get("latest_status")),
            tree_text("首次出现", data.get("first_seen")),
            tree_text("出场章节", data.get("appearances") or []),
            tree_text("备注", data.get("notes") or []),
        ])

    def save_current_config(self) -> None:
        save_config(self.api_key.get().strip(), self.base_url.get().strip(), self.model.get().strip())
        self.status.set("配置已保存。")

    def start_fetch_models(self) -> None:
        if not self.api_key.get().strip():
            messagebox.showwarning(APP_TITLE, "请先填写 API Key。")
            return
        self.save_current_config()
        self.status.set("正在获取模型列表...")
        threading.Thread(target=self.fetch_models_worker, daemon=True).start()

    def fetch_models_worker(self) -> None:
        try:
            models = fetch_models(self.api_key.get().strip(), self.base_url.get().strip() or DEFAULT_BASE_URL)
            self.events.put(("models", models))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("error", str(exc)))

    def start(self) -> None:
        if self.running:
            return
        if not self.project or not self.project.chapters:
            messagebox.showwarning(APP_TITLE, "请先导入或选择一本书。")
            return
        if not self.api_key.get().strip():
            messagebox.showwarning(APP_TITLE, "请填写 API Key。")
            return
        self.save_current_config()
        self.running = True
        self.paused = False
        self.pause_event.set()
        self.start_button.configure(state="disabled")
        self.pause_button.configure(state="normal", text="暂停")
        threading.Thread(target=self.worker, daemon=True).start()

    def toggle_pause(self) -> None:
        if not self.running:
            return
        self.paused = not self.paused
        if self.paused:
            self.pause_event.clear()
            self.pause_button.configure(text="继续")
            self.status.set("已暂停：当前请求完成后暂停下一章。")
        else:
            self.pause_event.set()
            self.pause_button.configure(text="暂停")
            self.status.set("已继续拆书。")

    def worker(self) -> None:
        assert self.project is not None
        api_key = self.api_key.get().strip()
        base_url = self.base_url.get().strip() or DEFAULT_BASE_URL
        model = self.model.get().strip() or DEFAULT_MODEL
        for index, chapter in enumerate(self.project.chapters, start=1):
            self.pause_event.wait()
            output_path = self.project.output_dir / outline_filename(index, chapter)
            if self.only_empty.get() and output_path.exists():
                chapter.outline = output_path.read_text(encoding="utf-8", errors="ignore")
                self.events.put(("done", index - 1))
                continue
            self.events.put(("working", index - 1))
            self.events.put(("status", f"正在拆解 {index}/{len(self.project.chapters)}：{chapter.title}"))
            try:
                context = build_outline_context(self.project.chapters, index - 1, self.character_registry)
                outline = normalize_outline_text(call_outline(api_key, base_url, model, chapter.title, chapter.text, context))
                output_path.write_text(outline, encoding="utf-8")
                chapter.outline = outline
                self.events.put(("status", f"正在更新角色信息 {index}/{len(self.project.chapters)}：{chapter.title}"))
                updated_context = build_outline_context(self.project.chapters, index, self.character_registry)
                self.character_registry = update_character_registry(
                    api_key, base_url, model, self.character_registry, chapter.title, chapter.text, updated_context
                )
                save_character_registry(self.project.characters_path, self.character_registry)
                save_state(self.project.book_dir, index - 1)
                self.events.put(("characters", None))
                self.events.put(("done", index - 1))
                time.sleep(0.5)
            except Exception as exc:  # noqa: BLE001
                self.events.put(("error", str(exc)))
                break
        self.events.put(("finished", None))

    def poll_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "status":
                self.status.set(str(payload))
            elif event == "models":
                models = list(payload)
                self.model_box.configure(values=models)
                if models and self.model.get() not in models:
                    self.model.set(models[0])
                self.save_current_config()
                self.status.set(f"已获取 {len(models)} 个模型。")
            elif event == "working":
                self.chapter_list.set(str(payload), "status", "处理中")
            elif event == "characters":
                self.refresh_character_view()
            elif event == "done":
                item = str(payload)
                self.chapter_list.set(item, "status", "已完成")
                self.chapter_list.selection_set(item)
                self.chapter_list.see(item)
                if self.project:
                    save_state(self.project.book_dir, int(item))
                self.show_selected()
            elif event == "error":
                messagebox.showerror(APP_TITLE, str(payload))
                self.status.set("操作失败，请检查 API Key、网络、接口地址或模型。")
            elif event == "finished":
                self.running = False
                self.paused = False
                self.pause_event.set()
                self.start_button.configure(state="normal")
                self.pause_button.configure(state="disabled", text="暂停")
                if self.project:
                    self.status.set(f"处理结束，结果已保存到：{self.project.output_dir}")
        self.root.after(200, self.poll_events)

    def on_close(self) -> None:
        self.save_current_config()
        selected = self.chapter_list.selection()
        selected_index = int(selected[0]) if selected and self.project else None
        save_state(
            self.project.book_dir if self.project else None,
            selected_index,
            geometry=self.root.geometry(),
            sash_positions=self.current_sash_positions(),
        )
        self.root.destroy()


def main() -> None:
    root = Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    ChaishuApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

"""
Torrent Downloader — интерфейс в стиле Windows 11 (Fluent / WinUI).

Зависимости:
    pip install customtkinter libtorrent
"""

import os
import sys
import ctypes

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
import libtorrent as lt

# ───────────────────────── Fluent-палитра (светлая, тёмная) ─────────────────────────
BG = ("#F3F3F3", "#202020")            # фон окна (Mica-подобный)
CARD = ("#FBFBFB", "#2B2B2B")          # фон карточек
CARD_BORDER = ("#E5E5E5", "#383838")
TEXT = ("#1A1A1A", "#FFFFFF")
TEXT_SECONDARY = ("#5C5C5C", "#C5C5C5")
TEXT_TERTIARY = ("#8A8A8A", "#9D9D9D")
ACCENT = ("#0067C0", "#60CDFF")
ACCENT_HOVER = ("#1975C5", "#4CB8EA")
ACCENT_TEXT = ("#FFFFFF", "#000000")
CONTROL = ("#FFFFFF", "#343434")
CONTROL_HOVER = ("#F6F6F6", "#3D3D3D")
TRACK = ("#E0E0E0", "#4A4A4A")
SUCCESS = ("#0F7B0F", "#6CCB5F")
ERROR = ("#C42B1C", "#FF99A4")
INFO_BG_OK = ("#DFF6DD", "#393D1B")
INFO_BG_ERR = ("#FDE7E9", "#442726")
INFO_BG_NEUTRAL = ("#F0F0F0", "#2F2F2F")

FONT = "Segoe UI Variable Display"  # при отсутствии шрифта Tk подставит Segoe UI / системный

STATE_NAMES = {
    0: "Ожидание проверки",
    1: "Проверка файлов",
    2: "Получение метаданных…",
    3: "Скачивание",
    4: "Завершено",
    5: "Раздача",
    6: "Выделение места",
    7: "Проверка данных",
}


# ───────────────────────── Вспомогательные функции ─────────────────────────
def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

def fmt_size(n: float) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if n < 1024 or unit == "ТБ":
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024


def fmt_speed(n: float) -> str:
    return fmt_size(n) + "/с"


def fmt_eta(seconds: float) -> str:
    if seconds <= 0 or seconds > 60 * 60 * 24 * 30:
        return "—"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} ч {m} мин"
    if m:
        return f"{m} мин {s} с"
    return f"{s} с"


# ───────────────────────── Компоненты ─────────────────────────
class Card(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(
            master,
            fg_color=CARD,
            border_width=1,
            border_color=CARD_BORDER,
            corner_radius=8,
            **kw,
        )


class AccentButton(ctk.CTkButton):
    def __init__(self, master, **kw):
        super().__init__(
            master,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT,
            text_color_disabled=("#FFFFFF", "#8A8A8A"),
            corner_radius=4,
            height=34,
            font=ctk.CTkFont(FONT, 13),
            **kw,
        )


class StandardButton(ctk.CTkButton):
    def __init__(self, master, **kw):
        super().__init__(
            master,
            fg_color=CONTROL,
            hover_color=CONTROL_HOVER,
            text_color=TEXT,
            text_color_disabled=TEXT_TERTIARY,
            border_width=1,
            border_color=CARD_BORDER,
            corner_radius=4,
            height=34,
            font=ctk.CTkFont(FONT, 13),
            **kw,
        )


class StatTile(ctk.CTkFrame):
    """Подпись + значение (как в панели свойств WinUI)."""

    def __init__(self, master, caption):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(
            self, text=caption, text_color=TEXT_TERTIARY,
            font=ctk.CTkFont(FONT, 11), anchor="w",
        ).pack(anchor="w")
        self.value = ctk.CTkLabel(
            self, text="—", text_color=TEXT,
            font=ctk.CTkFont(FONT, 14, "bold"), anchor="w",
        )
        self.value.pack(anchor="w")

    def set(self, text):
        self.value.configure(text=text)


# ───────────────────────── Приложение ─────────────────────────
class TorrentApp(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("system")  # следует теме Windows
        super().__init__(fg_color=BG)
        self.title("Torrent Downloader")
        self.geometry("620x640")
        self.minsize(560, 600)

        # customtkinter ставит свою иконку с задержкой, поэтому переопределяем позже
        self.after(250, lambda: self.iconbitmap(resource_path("app.ico")))

        self.ses = None
        self.handle = None
        self.paused = False
        self.after_id = None
        self.save_dir = str(Path.home() / "Downloads")

        self._build_ui()

    # ───── построение интерфейса ─────
    def _build_ui(self):
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=24, pady=(20, 16))

        # Заголовок страницы
        ctk.CTkLabel(
            root, text="Загрузки", text_color=TEXT,
            font=ctk.CTkFont(FONT, 28, "bold"), anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            root, text="Добавьте .torrent файл или magnet-ссылку",
            text_color=TEXT_SECONDARY, font=ctk.CTkFont(FONT, 13), anchor="w",
        ).pack(anchor="w", pady=(0, 16))

        # ── Карточка «Источник» ──
        src = Card(root)
        src.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(src, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=16)

        ctk.CTkLabel(
            inner, text="Источник", text_color=TEXT,
            font=ctk.CTkFont(FONT, 14, "bold"), anchor="w",
        ).pack(anchor="w", pady=(0, 8))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        self.entry_src = ctk.CTkEntry(
            row, height=34, corner_radius=4, border_width=1,
            fg_color=CONTROL, border_color=CARD_BORDER, text_color=TEXT,
            placeholder_text="magnet:?xt=… или путь к .torrent",
            font=ctk.CTkFont(FONT, 13),
        )
        self.entry_src.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.btn_browse = StandardButton(
            row, text="Обзор…", width=90, command=self.pick_torrent
        )
        self.btn_browse.grid(row=0, column=1)

        ctk.CTkLabel(
            inner, text="Папка сохранения", text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(FONT, 12), anchor="w",
        ).pack(anchor="w", pady=(14, 4))

        row2 = ctk.CTkFrame(inner, fg_color="transparent")
        row2.pack(fill="x")
        row2.columnconfigure(0, weight=1)
        self.entry_dir = ctk.CTkEntry(
            row2, height=34, corner_radius=4, border_width=1,
            fg_color=CONTROL, border_color=CARD_BORDER, text_color=TEXT,
            font=ctk.CTkFont(FONT, 13),
        )
        self.entry_dir.insert(0, self.save_dir)
        self.entry_dir.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.btn_dir = StandardButton(
            row2, text="Изменить", width=90, command=self.pick_dir
        )
        self.btn_dir.grid(row=0, column=1)

        self.btn_start = AccentButton(
            inner, text="Начать загрузку", command=self.start_download
        )
        self.btn_start.pack(anchor="w", pady=(16, 0))

        # ── Карточка «Текущая загрузка» ──
        dl = Card(root)
        dl.pack(fill="x", pady=(0, 12))
        d = ctk.CTkFrame(dl, fg_color="transparent")
        d.pack(fill="x", padx=16, pady=16)

        self.lbl_name = ctk.CTkLabel(
            d, text="Нет активной загрузки", text_color=TEXT,
            font=ctk.CTkFont(FONT, 15, "bold"), anchor="w",
            justify="left", wraplength=520,
        )
        self.lbl_name.pack(anchor="w")
        self.lbl_state = ctk.CTkLabel(
            d, text="Ожидание", text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(FONT, 12), anchor="w",
        )
        self.lbl_state.pack(anchor="w", pady=(2, 12))

        self.progress = ctk.CTkProgressBar(
            d, height=6, corner_radius=3,
            fg_color=TRACK, progress_color=ACCENT,
        )
        self.progress.set(0)
        self.progress.pack(fill="x")

        self.lbl_percent = ctk.CTkLabel(
            d, text="0 %", text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(FONT, 12), anchor="e",
        )
        self.lbl_percent.pack(anchor="e", pady=(4, 12))

        grid = ctk.CTkFrame(d, fg_color="transparent")
        grid.pack(fill="x")
        for i in range(4):
            grid.columnconfigure(i, weight=1, uniform="stat")
        self.t_speed = StatTile(grid, "Скорость")
        self.t_peers = StatTile(grid, "Пиры")
        self.t_size = StatTile(grid, "Загружено")
        self.t_eta = StatTile(grid, "Осталось")
        for i, t in enumerate((self.t_speed, self.t_peers, self.t_size, self.t_eta)):
            t.grid(row=0, column=i, sticky="w")

        ctrl = ctk.CTkFrame(d, fg_color="transparent")
        ctrl.pack(anchor="w", pady=(16, 0))
        self.btn_pause = StandardButton(
            ctrl, text="Пауза", width=110, command=self.toggle_pause, state="disabled"
        )
        self.btn_pause.pack(side="left", padx=(0, 8))
        self.btn_cancel = StandardButton(
            ctrl, text="Отменить", width=110, command=self.cancel, state="disabled"
        )
        self.btn_cancel.pack(side="left")

        # ── InfoBar внизу ──
        self.infobar = ctk.CTkFrame(
            root, fg_color=INFO_BG_NEUTRAL, corner_radius=4,
            border_width=1, border_color=CARD_BORDER,
        )
        self.infobar.pack(fill="x", side="bottom")
        self.lbl_info = ctk.CTkLabel(
            self.infobar, text="Готово к работе", text_color=TEXT,
            font=ctk.CTkFont(FONT, 12), anchor="w",
            justify="left", wraplength=540,
        )
        self.lbl_info.pack(fill="x", padx=12, pady=8)

    # ───── InfoBar ─────
    def info(self, text, kind="neutral"):
        bg = {"neutral": INFO_BG_NEUTRAL, "ok": INFO_BG_OK, "error": INFO_BG_ERR}[kind]
        self.infobar.configure(fg_color=bg)
        self.lbl_info.configure(text=text)

    # ───── выбор файлов ─────
    def pick_torrent(self):
        path = filedialog.askopenfilename(
            title="Выберите .torrent файл",
            filetypes=[("Torrent files", "*.torrent"), ("Все файлы", "*.*")],
        )
        if path:
            self.entry_src.delete(0, "end")
            self.entry_src.insert(0, path)

    def pick_dir(self):
        path = filedialog.askdirectory(title="Выберите папку для сохранения")
        if path:
            self.entry_dir.delete(0, "end")
            self.entry_dir.insert(0, path)

    # ───── управление загрузкой ─────
    def _set_idle(self, idle: bool):
        for w in (self.entry_src, self.entry_dir, self.btn_browse, self.btn_dir, self.btn_start):
            w.configure(state="normal" if idle else "disabled")
        for w in (self.btn_pause, self.btn_cancel):
            w.configure(state="disabled" if idle else "normal")
        if idle:
            self.btn_pause.configure(text="Пауза")

    def start_download(self):
        src = self.entry_src.get().strip()
        save_dir = self.entry_dir.get().strip()

        if not src:
            self.info("Укажите magnet-ссылку или выберите .torrent файл.", "error")
            return
        if not save_dir:
            self.info("Выберите папку для сохранения.", "error")
            return
        os.makedirs(save_dir, exist_ok=True)

        try:
            params = self._build_params(src, save_dir)
        except Exception as e:
            self.info(f"Не удалось прочитать источник: {e}", "error")
            return

        try:
            self.ses = lt.session()
            try:
                self.ses.apply_settings({"listen_interfaces": "0.0.0.0:6881"})
            except Exception:  # старые версии libtorrent
                self.ses.listen_on(6881, 6891)
            self.handle = self.ses.add_torrent(params)
        except Exception as e:
            self.info(f"Ошибка запуска загрузки: {e}", "error")
            return

        self.paused = False
        self.progress.set(0)
        self.progress.configure(progress_color=ACCENT)
        self.lbl_name.configure(text="Получение метаданных…")
        self._set_idle(False)
        self.info("Загрузка началась", "neutral")
        self._poll()

    @staticmethod
    def _build_params(src, save_dir):
        if src.lower().startswith("magnet:"):
            try:
                params = lt.parse_magnet_uri(src)
            except TypeError:  # libtorrent 1.1
                params = lt.add_torrent_params()
                lt.parse_magnet_uri(src, params)
        elif os.path.isfile(src):
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(src)
        else:
            raise ValueError("это не magnet-ссылка и не существующий файл")
        params.save_path = save_dir
        return params

    def toggle_pause(self):
        if not self.handle:
            return
        if self.paused:
            self.handle.resume()
            self.btn_pause.configure(text="Пауза")
            self.info("Загрузка продолжена")
        else:
            self.handle.pause()
            self.btn_pause.configure(text="Продолжить")
            self.info("Загрузка приостановлена")
        self.paused = not self.paused

    def cancel(self):
        self._stop()
        self.lbl_name.configure(text="Нет активной загрузки")
        self.lbl_state.configure(text="Отменено")
        self.progress.set(0)
        self.lbl_percent.configure(text="0 %")
        for t in (self.t_speed, self.t_peers, self.t_size, self.t_eta):
            t.set("—")
        self.info("Загрузка отменена")

    def _stop(self):
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        if self.ses and self.handle:
            try:
                self.ses.remove_torrent(self.handle)
            except Exception:
                pass
        self.handle = None
        self.ses = None
        self._set_idle(True)

    # ───── обновление интерфейса (в главном потоке) ─────
    def _poll(self):
        if not self.handle:
            return
        s = self.handle.status()

        if not s.has_metadata:
            self.lbl_state.configure(text="Получение метаданных…")
            self.t_peers.set(str(s.num_peers))
        else:
            self.lbl_name.configure(text=s.name)
            state = "Пауза" if self.paused else STATE_NAMES.get(int(s.state), "…")
            self.lbl_state.configure(text=state)

            self.progress.set(s.progress)
            self.lbl_percent.configure(text=f"{s.progress * 100:.1f} %")
            self.t_speed.set(fmt_speed(s.download_rate))
            self.t_peers.set(str(s.num_peers))
            self.t_size.set(f"{fmt_size(s.total_wanted_done)} / {fmt_size(s.total_wanted)}")

            remaining = s.total_wanted - s.total_wanted_done
            self.t_eta.set(
                fmt_eta(remaining / s.download_rate) if s.download_rate > 0 else "—"
            )

            if s.is_seeding or s.progress >= 1.0:
                self._finish(s.name)
                return

        self.after_id = self.after(500, self._poll)

    def _finish(self, name):
        self.progress.set(1)
        self.progress.configure(progress_color=SUCCESS)
        self.lbl_percent.configure(text="100 %")
        self.lbl_state.configure(text="Скачивание завершено")
        self.t_speed.set("—")
        self.t_eta.set("—")
        self._stop()
        self.info(f"«{name}» успешно скачан", "ok")


if __name__ == "__main__":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "TorrentDownloader.App"
        )
    except Exception:
        pass
    TorrentApp().mainloop()
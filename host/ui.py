"""ArtoDownloader Modern Dashboard UI (CustomTkinter tabanlı)."""
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
from PIL import Image
import customtkinter as ctk
import pystray
from history import HistoryManager

# CustomTkinter genel ayarlar
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

IPC_PORT = 58432

# Renk paleti
COLORS = {
    "bg": "#0f1117",
    "sidebar": "#161922",
    "card": "#1d212c",
    "card_hover": "#252b3a",
    "accent": "#4a72ff",
    "accent_hover": "#3a62ee",
    "green": "#2ec989",
    "amber": "#f59e0b",
    "red": "#ef4444",
    "text": "#f1f3f9",
    "text_muted": "#8b949e",
    "border": "#282e3e",
}

EXT_COLORS = {
    "ZIP": "#3b82f6", "RAR": "#8b5cf6", "7Z": "#6366f1",
    "ISO": "#ec4899", "EXE": "#ef4444", "MSI": "#f43f5e",
    "MP4": "#10b981", "MKV": "#059669", "MP3": "#14b8a6",
    "PDF": "#f97316", "DOC": "#0284c7", "XLS": "#16a34a"
}


def fmt_size(n):
    if not n:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def fmt_time(s):
    if not s or s <= 0:
        return "—"
    s = int(s)
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}s {m:02d}dk" if h else (f"{m}dk {sec:02d}sn" if m else f"{sec}sn")


def dark_titlebar(window):
    try:
        import ctypes
        window.update()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        v = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), 4)
    except Exception:
        pass


def get_icon_image():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for cand in [
        os.path.join(base, "assets", "icon.png"),
        os.path.join(base, "assets", "icon.ico"),
        os.path.join(os.path.dirname(__file__), "..", "assets", "icon.png")
    ]:
        if os.path.exists(cand):
            try:
                return Image.open(cand)
            except Exception:
                pass
    return Image.new("RGBA", (64, 64), (74, 114, 255, 255))


class ArtoDownloaderApp(ctk.CTk):
    def __init__(self, initial_args, EngineClass):
        super().__init__()

        self.title("⚡ ArtoDownloader")
        self.geometry("960x640")
        self.minsize(820, 520)
        self.configure(fg_color=COLORS["bg"])

        self.EngineClass = EngineClass
        self.history = HistoryManager()
        self.active_engines = {}  # {item_id: Engine}
        self.speed_stats = {}     # {item_id: {last_bytes, last_t, speed}}
        self.current_filter = "all"  # all | downloading | done | paused
        self.search_query = ""
        self.card_widgets = {}

        self.dest_dir = initial_args.dir or os.path.join(os.path.expanduser("~"), "Downloads")
        self.default_connections = initial_args.connections or 8
        os.makedirs(self.dest_dir, exist_ok=True)

        # İkon ayarı
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            ico = os.path.join(base, "assets", "icon.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

        dark_titlebar(self)

        # Layout kurulumu
        self.setup_ui()

        # Sistem tepsisi kurulumu
        self.setup_tray()

        # IPC sunucusu (tarayıcıdan gelen indirmeler)
        self.start_ipc_server()

        # İlk argüman varsa indirme ekle
        if initial_args.url:
            self.add_download(
                url=initial_args.url,
                filename=initial_args.filename,
                cookie=initial_args.cookie,
                referer=initial_args.referer,
                ua=initial_args.ua
            )

        # Düzenli UI güncelleme döngüsü
        self.after(300, self.update_loop)

        # Kapatma davranışı
        self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ---------------- SOL KENAR ÇUBUĞU (SIDEBAR) ----------------
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=COLORS["sidebar"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)

        # Logo ve Başlık
        self.logo_label = ctk.CTkLabel(
            self.sidebar,
            text="⚡ ArtoDownloader",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=COLORS["text"]
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(24, 4), sticky="w")

        self.subtitle_label = ctk.CTkLabel(
            self.sidebar,
            text="IDM Hızlandırıcı • v1.1",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["text_muted"]
        )
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

        # Filtre Butonları
        self.nav_btns = {}
        filters = [
            ("all", "📥 Tüm İndirmeler"),
            ("downloading", "⬇️ Aktif İndirilenler"),
            ("done", "✅ Tamamlananlar"),
            ("paused", "⏸️ Duraklatılanlar")
        ]

        for idx, (f_key, f_label) in enumerate(filters, start=2):
            btn = ctk.CTkButton(
                self.sidebar,
                text=f_label,
                anchor="w",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                fg_color=COLORS["card"] if f_key == "all" else "transparent",
                text_color=COLORS["text"],
                hover_color=COLORS["card_hover"],
                height=38,
                corner_radius=8,
                command=lambda k=f_key: self.set_filter(k)
            )
            btn.grid(row=idx, column=0, padx=12, pady=4, sticky="ew")
            self.nav_btns[f_key] = btn

        # Alt Butonlar (Sidebar Footer)
        self.btn_folder = ctk.CTkButton(
            self.sidebar,
            text="📁 İndirilenler Klasörü",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="transparent",
            text_color=COLORS["text_muted"],
            hover_color=COLORS["card_hover"],
            height=34,
            command=self.open_downloads_dir
        )
        self.btn_folder.grid(row=6, column=0, padx=12, pady=4, sticky="ew")

        self.btn_quit = ctk.CTkButton(
            self.sidebar,
            text="❌ Uygulamayı Kapat",
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="transparent",
            text_color="#f87171",
            hover_color="#3b1d24",
            height=34,
            command=self.quit_completely
        )
        self.btn_quit.grid(row=7, column=0, padx=12, pady=(4, 16), sticky="ew")

        # ---------------- SAĞ ANA ALAN (MAIN CONTENT) ----------------
        self.main_area = ctk.CTkFrame(self, corner_radius=0, fg_color=COLORS["bg"])
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_rowconfigure(1, weight=1)

        # Üst Araç Çubuğu (Top Bar)
        self.top_bar = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.top_bar.grid_columnconfigure(1, weight=1)

        # + Yeni İndirme Butonu
        self.btn_add = ctk.CTkButton(
            self.top_bar,
            text="➕ Yeni İndirme Ekle",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            height=38,
            corner_radius=8,
            command=self.prompt_add_download
        )
        self.btn_add.grid(row=0, column=0, padx=(0, 12), sticky="w")

        # Arama Kutusu
        self.search_entry = ctk.CTkEntry(
            self.top_bar,
            placeholder_text="🔍 Dosyalarda ara...",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=COLORS["card"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            height=38,
            corner_radius=8
        )
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        self.search_entry.bind("<KeyRelease>", self.on_search)

        # Tamamlananları Temizle
        self.btn_clean = ctk.CTkButton(
            self.top_bar,
            text="🧹 Temizle",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=COLORS["card"],
            hover_color=COLORS["card_hover"],
            text_color=COLORS["text_muted"],
            width=80,
            height=38,
            corner_radius=8,
            command=self.clear_completed
        )
        self.btn_clean.grid(row=0, column=2, padx=(0, 8))

        # Tepsiye Küçült Butonu
        self.btn_minimize = ctk.CTkButton(
            self.top_bar,
            text="🗕 Tepsiye Küçült",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=COLORS["card"],
            hover_color=COLORS["card_hover"],
            text_color=COLORS["text_muted"],
            width=110,
            height=38,
            corner_radius=8,
            command=self.minimize_to_tray
        )
        self.btn_minimize.grid(row=0, column=3)

        # Kaydırılabilir İndirme Listesi (Scrollable Frame)
        self.scroll_list = ctk.CTkScrollableFrame(
            self.main_area,
            fg_color="transparent",
            corner_radius=0
        )
        self.scroll_list.grid(row=1, column=0, sticky="nsew")
        self.scroll_list.grid_columnconfigure(0, weight=1)

        # İlk render
        self.render_downloads()

    def set_filter(self, f_key):
        self.current_filter = f_key
        for k, btn in self.nav_btns.items():
            btn.configure(fg_color=COLORS["card"] if k == f_key else "transparent")
        self.render_downloads()

    def on_search(self, event=None):
        self.search_query = self.search_entry.get().strip().lower()
        self.render_downloads()

    def render_downloads(self):
        # Önceki kartları temizle
        for widget in self.scroll_list.winfo_children():
            widget.destroy()
        self.card_widgets.clear()

        items = self.history.items

        # Filtrele
        if self.current_filter != "all":
            items = [it for it in items if it.get("status") == self.current_filter]

        # Arama
        if self.search_query:
            items = [it for it in items if self.search_query in it.get("filename", "").lower()]

        if not items:
            empty_frame = ctk.CTkFrame(self.scroll_list, fg_color="transparent")
            empty_frame.pack(pady=80, fill="both", expand=True)

            msg = "Henüz bir indirme yok."
            if self.search_query:
                msg = f"'{self.search_query}' ile eşleşen indirme bulunamadı."
            elif self.current_filter != "all":
                msg = f"Bu kategoride indirme yok."

            lbl = ctk.CTkLabel(
                empty_frame,
                text=msg,
                font=ctk.CTkFont(family="Segoe UI", size=15),
                text_color=COLORS["text_muted"]
            )
            lbl.pack(pady=10)

            if not self.search_query and self.current_filter == "all":
                sub = ctk.CTkLabel(
                    empty_frame,
                    text="LibreWolf'tan bir dosya indirin veya yukarıdaki '+ Yeni İndirme Ekle' butonunu kullanın.",
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    text_color=COLORS["text_muted"]
                )
                sub.pack(pady=4)
            return

        for item in items:
            self.create_download_card(item)

    def create_download_card(self, item):
        item_id = item["id"]
        fname = item.get("filename") or "İndirme"
        status = item.get("status", "paused")
        total = item.get("total_bytes", 0)
        done = item.get("downloaded_bytes", 0)

        ext = os.path.splitext(fname)[1].lstrip(".").upper()[:4] or "FILE"
        ext_color = EXT_COLORS.get(ext, COLORS["accent"])

        card = ctk.CTkFrame(
            self.scroll_list,
            fg_color=COLORS["card"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border"]
        )
        card.pack(fill="x", pady=6, padx=4)
        card.grid_columnconfigure(1, weight=1)

        # Uzantı Rozeti
        badge = ctk.CTkLabel(
            card,
            text=ext,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=ext_color,
            text_color="#ffffff",
            width=54,
            height=54,
            corner_radius=8
        )
        badge.grid(row=0, column=0, rowspan=2, padx=14, pady=14)

        # Bilgi Alanı (Orta)
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(12, 4))
        info_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            info_frame,
            text=fname if len(fname) < 55 else fname[:52] + "...",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=COLORS["text"],
            anchor="w"
        )
        title.grid(row=0, column=0, sticky="w")

        # İlerleme Çubuğu
        pct = (done / total) if (total and total > 0) else 0.0
        pct = max(0.0, min(1.0, pct))
        if status == "done":
            pct = 1.0

        pbar = ctk.CTkProgressBar(
            info_frame,
            height=6,
            corner_radius=3,
            progress_color=COLORS["green"] if status == "done" else COLORS["accent"]
        )
        pbar.set(pct)
        pbar.grid(row=1, column=0, sticky="ew", pady=(6, 4))

        # Alt Durum Satırı
        status_lbl = ctk.CTkLabel(
            info_frame,
            text=self.format_status_text(item),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["text_muted"],
            anchor="w"
        )
        status_lbl.grid(row=2, column=0, sticky="w")

        # Sağ Butonlar
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.grid(row=0, column=2, rowspan=2, padx=14, pady=14, sticky="e")

        actions = self.get_card_actions(item)
        for act_text, act_cmd, act_col in actions:
            b = ctk.CTkButton(
                btn_frame,
                text=act_text,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                fg_color=act_col,
                hover_color=COLORS["card_hover"],
                text_color=COLORS["text"],
                width=72,
                height=30,
                corner_radius=6,
                command=act_cmd
            )
            b.pack(side="left", padx=3)

        self.card_widgets[item_id] = {
            "pbar": pbar,
            "status_lbl": status_lbl,
            "card": card,
            "btn_frame": btn_frame
        }

    def format_status_text(self, item):
        status = item.get("status")
        total = item.get("total_bytes", 0)
        done = item.get("downloaded_bytes", 0)
        speed = item.get("speed", 0)

        if status == "downloading":
            pct = (done * 100 / total) if total else 0
            eta = ""
            if speed > 0 and total:
                rem = max(0, total - done)
                eta = f" • Kalan: {fmt_time(rem / speed)}"
            return f"{fmt_size(done)} / {fmt_size(total)} (%{pct:.1f}) • ⚡ {fmt_size(speed)}/s{eta}"
        elif status == "done":
            return f"{fmt_size(total)} • Tamamlandı • {item.get('created_at', '')}"
        elif status == "paused":
            return f"{fmt_size(done)} / {fmt_size(total)} • Duraklatıldı"
        elif status == "error":
            return f"Hata: {item.get('error', 'Bilinmeyen hata')}"
        return f"{fmt_size(done)} / {fmt_size(total)}"

    def get_card_actions(self, item):
        item_id = item["id"]
        status = item.get("status")
        filepath = item.get("filepath", "")

        actions = []
        if status == "downloading":
            actions.append(("⏸ Duraklat", lambda: self.pause_download(item_id), COLORS["border"]))
            actions.append(("❌ İptal", lambda: self.cancel_download(item_id), "#7f1d1d"))
        elif status == "paused":
            actions.append(("▶ Devam", lambda: self.resume_download(item_id), COLORS["accent"]))
            actions.append(("🗑 Sil", lambda: self.delete_download(item_id), COLORS["border"]))
        elif status == "done":
            actions.append(("📁 Klasör", lambda: self.open_in_folder(filepath), COLORS["border"]))
            actions.append(("▶ Aç", lambda: self.open_file(filepath), COLORS["green"]))
            actions.append(("🗑 Sil", lambda: self.delete_download(item_id), COLORS["border"]))
        elif status == "error":
            actions.append(("🔄 Tekrar", lambda: self.resume_download(item_id), COLORS["accent"]))
            actions.append(("🗑 Sil", lambda: self.delete_download(item_id), COLORS["border"]))
        return actions

    # ---------------- İNDİRME AKSİYONLARI ----------------
    def prompt_add_download(self):
        dialog = ctk.CTkInputDialog(text="İndirme bağlantısını (URL) girin:", title="Yeni İndirme Ekle")
        url = dialog.get_input()
        if url and url.strip().lower().startswith(("http://", "https://")):
            self.add_download(url=url.strip())

    def add_download(self, url, filename="", cookie="", referer="", ua=""):
        item_id = str(int(time.time() * 1000))
        fname = filename or url.split("/")[-1].split("?")[0] or f"download_{item_id[:6]}"

        item = {
            "id": item_id,
            "url": url,
            "filename": fname,
            "filepath": os.path.join(self.dest_dir, fname),
            "total_bytes": 0,
            "downloaded_bytes": 0,
            "status": "downloading",
            "created_at": time.strftime("%d.%m.%Y %H:%M"),
            "speed": 0,
            "cookie": cookie,
            "referer": referer,
            "ua": ua,
            "error": None
        }

        self.history.add(item)
        self.render_downloads()
        self.show_window()

        # Engine başlat
        headers = {"User-Agent": ua or "Mozilla/5.0", "Accept": "*/*", "Accept-Encoding": "identity"}
        if referer:
            headers["Referer"] = referer
        if cookie:
            headers["Cookie"] = cookie

        eng = self.EngineClass(url, self.dest_dir, headers, fname, self.default_connections)
        self.active_engines[item_id] = eng
        self.speed_stats[item_id] = {"last_bytes": 0, "last_t": time.time(), "speed": 0}

        def run_task():
            try:
                eng.probe()
                eng.prepare()
                # Dosya adını sunucunun verdiği nihai ada güncelle
                self.history.update(
                    item_id,
                    filename=eng.filename,
                    filepath=os.path.join(self.dest_dir, eng.filename),
                    total_bytes=eng.total
                )
                eng.start()
            except Exception as e:
                eng.error = str(e)
                eng.state = "error"
                self.history.update(item_id, status="error", error=str(e))

        threading.Thread(target=run_task, daemon=True).start()

    def pause_download(self, item_id):
        eng = self.active_engines.get(item_id)
        if eng:
            eng.pause()
            self.history.update(item_id, status="paused", speed=0)
            self.render_downloads()

    def resume_download(self, item_id):
        item = next((it for it in self.history.items if it["id"] == item_id), None)
        if not item:
            return
        eng = self.active_engines.get(item_id)
        if not eng:
            headers = {"User-Agent": item.get("ua") or "Mozilla/5.0", "Accept": "*/*", "Accept-Encoding": "identity"}
            if item.get("referer"):
                headers["Referer"] = item.get("referer")
            if item.get("cookie"):
                headers["Cookie"] = item.get("cookie")
            eng = self.EngineClass(item["url"], self.dest_dir, headers, item.get("filename"), self.default_connections)
            self.active_engines[item_id] = eng
            self.speed_stats[item_id] = {"last_bytes": 0, "last_t": time.time(), "speed": 0}

            def run_resume():
                try:
                    eng.probe()
                    eng.prepare()
                    eng.start()
                except Exception as e:
                    eng.error = str(e)
                    eng.state = "error"
                    self.history.update(item_id, status="error", error=str(e))

            threading.Thread(target=run_resume, daemon=True).start()
        else:
            eng.start()

        self.history.update(item_id, status="downloading", error=None)
        self.render_downloads()

    def cancel_download(self, item_id):
        eng = self.active_engines.get(item_id)
        if eng:
            eng.cancel()
        self.history.remove(item_id, delete_file=True)
        if item_id in self.active_engines:
            del self.active_engines[item_id]
        if item_id in self.speed_stats:
            del self.speed_stats[item_id]
        self.render_downloads()

    def delete_download(self, item_id):
        eng = self.active_engines.get(item_id)
        if eng:
            eng.cancel()
        self.history.remove(item_id, delete_file=False)
        if item_id in self.active_engines:
            del self.active_engines[item_id]
        self.render_downloads()

    def clear_completed(self):
        self.history.clear_completed()
        self.render_downloads()

    def open_in_folder(self, filepath):
        if filepath and os.path.exists(filepath):
            subprocess.Popen(["explorer", "/select,", filepath])
        elif os.path.exists(self.dest_dir):
            subprocess.Popen(["explorer", self.dest_dir])

    def open_file(self, filepath):
        if filepath and os.path.exists(filepath):
            os.startfile(filepath)

    def open_downloads_dir(self):
        if os.path.exists(self.dest_dir):
            subprocess.Popen(["explorer", self.dest_dir])

    # ---------------- CANLI GÜNCELLEME DÖNGÜSÜ ----------------
    def update_loop(self):
        now = time.time()
        needs_rerender = False

        for item_id, eng in list(self.active_engines.items()):
            item = next((it for it in self.history.items if it["id"] == item_id), None)
            if not item:
                continue

            st = eng.state
            done = eng.downloaded()
            total = eng.total

            # Hız hesapla
            stat = self.speed_stats.get(item_id, {"last_bytes": 0, "last_t": now, "speed": 0})
            dt = now - stat["last_t"]
            if dt >= 0.5:
                inst_speed = max(0, eng.session_bytes - stat["last_bytes"]) / dt
                stat["speed"] = inst_speed if stat["speed"] == 0 else (stat["speed"] * 0.6 + inst_speed * 0.4)
                stat["last_bytes"] = eng.session_bytes
                stat["last_t"] = now

            speed = stat["speed"] if st == "downloading" else 0

            # Verileri güncelle
            item["downloaded_bytes"] = done
            if total > 0:
                item["total_bytes"] = total
            item["speed"] = speed

            old_st = item.get("status")
            if st != old_st:
                item["status"] = st
                needs_rerender = True

            # UI kartını doğrudan güncelle
            widgets = self.card_widgets.get(item_id)
            if widgets:
                pct = (done / total) if (total and total > 0) else 0.0
                widgets["pbar"].set(max(0.0, min(1.0, pct)))
                widgets["status_lbl"].configure(text=self.format_status_text(item))

            if st in ("done", "error", "cancelled") and item_id in self.active_engines:
                self.history.update(
                    item_id,
                    status=st,
                    downloaded_bytes=done,
                    total_bytes=total,
                    error=eng.error
                )
                if st == "done":
                    del self.active_engines[item_id]
                    needs_rerender = True

        if needs_rerender:
            self.render_downloads()

        self.after(400, self.update_loop)

    # ---------------- SİSTEM TEPSİSİ & PENCERE KONTROLÜ ----------------
    def setup_tray(self):
        tray_img = get_icon_image()
        tray_menu = pystray.Menu(
            pystray.MenuItem("ArtoDownloader'ı Göster", self.show_window, default=True),
            pystray.MenuItem("Yeni İndirme Ekle...", lambda: self.after(0, self.prompt_add_download)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Tamamen Çıkış", self.quit_completely)
        )
        self.tray = pystray.Icon("ArtoDownloader", tray_img, "ArtoDownloader", menu=tray_menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def show_window(self, icon=None, item=None):
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def minimize_to_tray(self):
        self.withdraw()

    def quit_completely(self, icon=None, item=None):
        for eng in self.active_engines.values():
            try:
                eng.pause()
            except Exception:
                pass
        if hasattr(self, "tray") and self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.after(0, self.destroy)

    # ---------------- YEREL IPC SUNUCUSU ----------------
    def start_ipc_server(self):
        def run_server():
            try:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(("127.0.0.1", IPC_PORT))
                srv.listen(5)
                while True:
                    conn, _ = srv.accept()
                    try:
                        raw_len = conn.recv(4)
                        if len(raw_len) == 4:
                            length = struct.unpack("=I", raw_len)[0]
                            data = b""
                            while len(data) < length:
                                chunk = conn.recv(length - len(data))
                                if not chunk:
                                    break
                                data += chunk
                            msg = json.loads(data.decode("utf-8"))
                            self.after(0, lambda m=msg: self.add_download(
                                url=m.get("url", ""),
                                filename=m.get("filename", ""),
                                cookie=m.get("cookie", ""),
                                referer=m.get("referrer", ""),
                                ua=m.get("userAgent", "")
                            ))
                            resp = json.dumps({"ok": True}).encode("utf-8")
                            conn.sendall(struct.pack("=I", len(resp)) + resp)
                    except Exception:
                        pass
                    finally:
                        conn.close()
            except Exception:
                pass

        threading.Thread(target=run_server, daemon=True).start()


def run_gui(args, EngineClass, fmt_size_func=None):
    app = ArtoDownloaderApp(args, EngineClass)
    app.mainloop()

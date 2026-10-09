"""ArtoDownloader modern arayüz (tkinter, canvas tabanlı koyu tema, Sistem Tepsisi ve IPC)."""
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import simpledialog, ttk
import urllib.parse
from PIL import Image
import pystray

BG = "#0f1117"
CARD = "#171a23"
CARD2 = "#1e2230"
LINE = "#2a2f42"
TEXT = "#e8eaf2"
MUTED = "#8b91a8"
ACCENT = "#6c8cff"
ACCENT2 = "#9b6cff"
GREEN = "#38d39f"
RED = "#ff5c7a"
AMBER = "#ffb84d"
FONT = "Segoe UI"
IPC_PORT = 58432


def rounded(c, x1, y1, x2, y2, r, **kw):
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1
    ]
    return c.create_polygon(pts, smooth=True, **kw)


def lerp(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Button(tk.Canvas):
    def __init__(self, parent, text, command, color=ACCENT, w=130, h=38):
        super().__init__(parent, width=w, height=h, bg=CARD, highlightthickness=0, cursor="hand2")
        self.w, self.h, self.command, self.color, self.text = w, h, command, color, text
        self.enabled = True
        self.hover = False
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False))
        self.bind("<Button-1>", lambda e: self.enabled and self.command())
        self.draw()

    def _set(self, hover):
        self.hover = hover
        self.draw()

    def configure_btn(self, text=None, color=None, enabled=None):
        if text is not None:
            self.text = text
        if color is not None:
            self.color = color
        if enabled is not None:
            self.enabled = enabled
        self.draw()

    def draw(self):
        self.delete("all")
        col = self.color if self.enabled else LINE
        if self.hover and self.enabled:
            col = lerp(col, "#ffffff", 0.15)
        rounded(self, 1, 1, self.w - 1, self.h - 1, 10, fill=col, outline="")
        self.create_text(
            self.w / 2, self.h / 2, text=self.text,
            fill="#ffffff" if self.enabled else MUTED,
            font=(FONT, 10, "bold")
        )
        self.config(cursor="hand2" if self.enabled else "arrow")


def dark_titlebar(root):
    try:
        import ctypes
        root.update()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        v = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), 4)
    except Exception:
        pass


def fmt_time(s):
    s = int(s)
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}s {m:02d}dk" if h else (f"{m}dk {sec:02d}sn" if m else f"{sec}sn")


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
    return Image.new("RGBA", (64, 64), (108, 140, 255, 255))


def run_gui(args, Engine, fmt_size):
    headers = {"User-Agent": args.ua or "Mozilla/5.0", "Accept": "*/*", "Accept-Encoding": "identity"}
    if args.referer:
        headers["Referer"] = args.referer
    if args.cookie:
        headers["Cookie"] = args.cookie
    dest_dir = args.dir or os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(dest_dir, exist_ok=True)

    current_engine = [Engine(args.url, dest_dir, headers, args.filename, args.connections)]

    W, H = 680, 650
    root = tk.Tk()
    root.title("ArtoDownloader")
    try:
        base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        ico = os.path.join(base, "assets", "icon.ico")
        if os.path.exists(ico):
            root.iconbitmap(ico)
    except Exception:
        pass

    root.configure(bg=BG)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")
    root.resizable(False, False)
    dark_titlebar(root)
    root.attributes("-topmost", True)
    root.after(1200, lambda: root.attributes("-topmost", False))
    root.lift()
    root.focus_force()

    current_host = [urllib.parse.urlparse(args.url).netloc if args.url else ""]

    # ---- Kart: başlık ----
    head = tk.Canvas(root, width=W - 40, height=110, bg=BG, highlightthickness=0)
    head.place(x=20, y=18)
    # ---- Kart: ilerleme / segmentler / grafik ----
    body = tk.Canvas(root, width=W - 40, height=340, bg=BG, highlightthickness=0)
    body.place(x=20, y=136)
    # ---- Butonlar ----
    footer = tk.Frame(root, bg=BG)
    footer.place(x=20, y=H - 62)

    pause_btn = Button(footer, "Duraklat", lambda: toggle(), ACCENT, 150)
    pause_btn.pack(side="left")
    cancel_btn = Button(footer, "İptal", lambda: cancel(), "#3a3f55", 110)
    cancel_btn.pack(side="left", padx=10)
    folder_btn = Button(footer, "Klasörü Aç", lambda: open_folder(), "#3a3f55", 130)
    file_btn = Button(footer, "Dosyayı Aç", lambda: open_file(), GREEN, 130)

    speeds = []
    state = {
        "speed": 0.0, "last_bytes": 0, "last_t": time.time(),
        "peak": 1.0, "phase": 0.0, "avg_sum": 0.0, "avg_n": 0
    }

    # ==================== SİSTEM TEPSİSİ (SYSTEM TRAY) ====================
    tray_icon_holder = [None]

    def show_window(icon=None, item=None):
        root.after(0, lambda: (root.deiconify(), root.lift(), root.focus_force()))

    def minimize_to_tray():
        root.withdraw()

    def prompt_new_download(icon=None, item=None):
        def _ask():
            show_window()
            new_url = simpledialog.askstring("Yeni İndirme", "İndirme URL'sini yapıştırın:", parent=root)
            if new_url and new_url.lower().startswith(("http://", "https://")):
                start_new_download({"url": new_url})
        root.after(0, _ask)

    def quit_completely(icon=None, item=None):
        eng = current_engine[0]
        if eng:
            eng.pause()
        if tray_icon_holder[0]:
            try:
                tray_icon_holder[0].stop()
            except Exception:
                pass
        root.after(0, root.destroy)

    tray_menu = pystray.Menu(
        pystray.MenuItem("ArtoDownloader'ı Göster", show_window, default=True),
        pystray.MenuItem("Yeni İndirme Ekle...", prompt_new_download),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Çıkış", quit_completely)
    )

    tray_img = get_icon_image()
    tray_icon = pystray.Icon("ArtoDownloader", tray_img, "ArtoDownloader", menu=tray_menu)
    tray_icon_holder[0] = tray_icon

    threading.Thread(target=tray_icon.run, daemon=True).start()

    # Kapat butonuna basıldığında tamamen çıkmak yerine tepsiye küçül
    root.protocol("WM_DELETE_WINDOW", minimize_to_tray)

    # ==================== İNDİRME YÖNETİMİ ====================
    def toggle():
        eng = current_engine[0]
        if not eng.url:
            prompt_new_download()
        elif eng.state == "downloading":
            eng.pause()
        elif eng.state in ("paused", "error"):
            eng.start()

    def cancel():
        eng = current_engine[0]
        if eng.state == "downloading":
            eng.cancel()
            minimize_to_tray()
        else:
            if eng.filename and eng.state != "done":
                for p in eng._paths()[1:]:
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except Exception:
                            pass
            minimize_to_tray()

    def open_folder():
        eng = current_engine[0]
        if os.name == "nt" and eng.filename:
            subprocess.Popen(["explorer", "/select,", os.path.join(dest_dir, eng.filename)])

    def open_file():
        eng = current_engine[0]
        if os.name == "nt" and eng.filename:
            os.startfile(os.path.join(dest_dir, eng.filename))

    def init_engine(eng):
        try:
            eng.probe()
            eng.prepare()
            eng.start()
        except Exception as e:
            eng.error = str(e)
            eng.state = "error"

    if args.url:
        threading.Thread(target=lambda: init_engine(current_engine[0]), daemon=True).start()
    else:
        current_engine[0].state = "paused"

    def start_new_download(msg):
        url = msg.get("url", "")
        if not url:
            return
        eng = current_engine[0]
        if eng and eng.state == "downloading":
            eng.pause()

        new_h = dict(headers)
        if msg.get("referrer"):
            new_h["Referer"] = msg.get("referrer")
        if msg.get("cookie"):
            new_h["Cookie"] = msg.get("cookie")
        if msg.get("userAgent"):
            new_h["User-Agent"] = msg.get("userAgent")

        new_eng = Engine(url, dest_dir, new_h, msg.get("filename", ""), args.connections)
        current_engine[0] = new_eng
        current_host[0] = urllib.parse.urlparse(url).netloc
        speeds.clear()
        state["speed"] = 0.0
        state["last_bytes"] = 0
        state["last_t"] = time.time()
        state["peak"] = 1.0

        if not pause_btn.winfo_ismapped():
            pause_btn.pack(side="left")
        cancel_btn.configure_btn("İptal")
        folder_btn.pack_forget()
        file_btn.pack_forget()

        show_window()
        threading.Thread(target=lambda: init_engine(new_eng), daemon=True).start()

    # ==================== YEREL IPC SUNUCUSU (BROWSER'DAN GÖNDERİLENLER) ====================
    def run_ipc_server():
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
                        root.after(0, lambda m=msg: start_new_download(m))
                        resp = json.dumps({"ok": True}).encode("utf-8")
                        conn.sendall(struct.pack("=I", len(resp)) + resp)
                except Exception:
                    pass
                finally:
                    conn.close()
        except Exception:
            pass

    threading.Thread(target=run_ipc_server, daemon=True).start()

    # ==================== ÇİZİM VE GÜNCELLEME ====================
    def draw_header(color, status):
        eng = current_engine[0]
        head.delete("all")
        rounded(head, 0, 0, W - 40, 110, 16, fill=CARD, outline="")
        name = eng.filename or "Bağlanılıyor…"
        ext = os.path.splitext(name)[1].lstrip(".").upper()[:4] or "FILE"
        rounded(head, 20, 25, 80, 85, 14, fill=lerp(color, BG, 0.65), outline="")
        rounded(head, 20, 25, 80, 85, 14, fill="", outline=color, width=2)
        head.create_text(50, 55, text=ext, fill=color, font=(FONT, 11, "bold"))
        shown = name if len(name) < 44 else name[:41] + "…"
        head.create_text(100, 40, text=shown, anchor="w", fill=TEXT, font=(FONT, 15, "bold"))
        head.create_text(100, 66, text=current_host[0], anchor="w", fill=MUTED, font=(FONT, 10))
        bw = 12 + len(status) * 8
        rounded(head, 98, 78, 98 + bw, 100, 11, fill=lerp(color, CARD, 0.78), outline="")
        head.create_text(98 + bw / 2, 89, text=status, fill=color, font=(FONT, 9, "bold"))

    def draw_body(color, done, total, speed, pct):
        eng = current_engine[0]
        c = body
        c.delete("all")
        bw = W - 40
        # --- büyük hız + yüzde ---
        rounded(c, 0, 0, bw, 130, 16, fill=CARD, outline="")
        c.create_text(28, 30, text="İNDİRME HIZI", anchor="w", fill=MUTED, font=(FONT, 9, "bold"))
        sp = fmt_size(speed) + "/s"
        c.create_text(28, 66, text=sp, anchor="w", fill=TEXT, font=(FONT, 28, "bold"))
        c.create_text(bw - 28, 30, text="TAMAMLANAN", anchor="e", fill=MUTED, font=(FONT, 9, "bold"))
        c.create_text(
            bw - 28, 66, text=f"%{pct:.1f}" if total else "—", anchor="e", fill=color,
            font=(FONT, 28, "bold")
        )
        # ilerleme çubuğu
        x1, x2, y1, y2 = 28, bw - 28, 102, 116
        rounded(c, x1, y1, x2, y2, 7, fill=CARD2, outline="")
        if total:
            fw = max(14, (x2 - x1) * pct / 100) if pct > 0 else 0
            if fw:
                steps = 24
                for i in range(steps):
                    sx1 = x1 + fw * i / steps
                    sx2 = x1 + fw * (i + 1) / steps
                    col = lerp(ACCENT, ACCENT2, i / steps) if eng.state != "done" else GREEN
                    if i == 0:
                        rounded(c, x1, y1, x1 + max(14, fw / steps + 8), y2, 7, fill=col, outline="")
                    else:
                        c.create_rectangle(sx1, y1, sx2 + 1, y2, fill=col, outline="")
                if fw >= 14:
                    rounded(
                        c, x1 + fw - 14, y1, x1 + fw, y2, 7,
                        fill=lerp(ACCENT, ACCENT2, 1) if eng.state != "done" else GREEN, outline=""
                    )
        else:
            ph = state["phase"] % 1.0
            sx = x1 + (x2 - x1 - 80) * ph
            rounded(c, sx, y1, sx + 80, y2, 7, fill=ACCENT, outline="")

        # --- segment haritası ---
        top = 144
        rounded(c, 0, top, bw, top + 70, 16, fill=CARD, outline="")
        c.create_text(28, top + 20, text="PARÇA HARİTASI", anchor="w", fill=MUTED, font=(FONT, 9, "bold"))
        nseg = sum(1 for s in eng.segs if s.active) if eng.resumable else (1 if eng.state == "downloading" else 0)
        c.create_text(bw - 28, top + 20, text=f"{nseg} aktif bağlantı", anchor="e", fill=MUTED, font=(FONT, 9))
        mx1, mx2, my1, my2 = 28, bw - 28, top + 36, top + 54
        rounded(c, mx1, my1, mx2, my2, 5, fill=CARD2, outline="")
        if eng.resumable and total:
            with eng.lock:
                segs = [(s.start, s.end, s.pos, s.active) for s in eng.segs]
            span = mx2 - mx1
            for st, en, pos, act in sorted(segs):
                a = mx1 + span * st / total
                b = mx1 + span * (min(pos, en + 1)) / total
                e = mx1 + span * (en + 1) / total
                col = ACCENT if act else (GREEN if pos > en else MUTED)
                if b - a >= 1:
                    c.create_rectangle(a, my1 + 2, b, my2 - 2, fill=col, outline="")
                if act and e - b > 1:
                    c.create_rectangle(b, my1 + 2, min(e, b + 3), my2 - 2, fill="#ffffff", outline="")
                if a > mx1 + 1:
                    c.create_line(a, my1, a, my2, fill=BG)

        # --- hız grafiği ---
        gtop = 228
        rounded(c, 0, gtop, bw, gtop + 112, 16, fill=CARD, outline="")
        c.create_text(28, gtop + 20, text="HIZ GRAFİĞİ", anchor="w", fill=MUTED, font=(FONT, 9, "bold"))
        avg = state["avg_sum"] / state["avg_n"] if state["avg_n"] else 0
        c.create_text(
            bw - 28, gtop + 20, text=f"ort. {fmt_size(avg)}/s   •   zirve {fmt_size(state['peak'])}/s",
            anchor="e", fill=MUTED, font=(FONT, 9)
        )
        gx1, gx2, gy1, gy2 = 28, bw - 28, gtop + 38, gtop + 98
        for i in range(4):
            y = gy1 + (gy2 - gy1) * i / 3
            c.create_line(gx1, y, gx2, y, fill=LINE, dash=(2, 4))
        if len(speeds) > 1:
            peak = max(max(speeds), 1.0) * 1.15
            n = 90
            pts = []
            data = speeds[-n:]
            for i, v in enumerate(data):
                x = gx2 - (len(data) - 1 - i) * (gx2 - gx1) / (n - 1)
                y = gy2 - (gy2 - gy1) * v / peak
                pts.append((x, y))
            poly = [pts[0][0], gy2] + [v for p in pts for v in p] + [pts[-1][0], gy2]
            c.create_polygon(poly, fill=lerp(color, CARD, 0.8), outline="")
            c.create_line([v for p in pts for v in p], fill=color, width=2, smooth=True)
            c.create_oval(
                pts[-1][0] - 4, pts[-1][1] - 4, pts[-1][0] + 4, pts[-1][1] + 4,
                fill=color, outline=CARD, width=2
            )

    def draw_stats(done, total, speed):
        eng = current_engine[0]
        stats.delete("all")
        items = [
            ("BOYUT", fmt_size(total) if total else "Bilinmiyor"),
            ("İNDİRİLEN", fmt_size(done)),
            ("KALAN SÜRE", fmt_time((total - done) / speed) if speed > 1 and total and eng.state == "downloading" else "—"),
            ("KONUM", "İndirilenler")
        ]
        cw = (W - 40 - 30) / 4
        for i, (k, v) in enumerate(items):
            x = i * (cw + 10)
            rounded(stats, x, 0, x + cw, 58, 12, fill=CARD, outline="")
            stats.create_text(x + 14, 17, text=k, anchor="w", fill=MUTED, font=(FONT, 8, "bold"))
            stats.create_text(x + 14, 39, text=v, anchor="w", fill=TEXT, font=(FONT, 11, "bold"))

    stats = tk.Canvas(root, width=W - 40, height=58, bg=BG, highlightthickness=0)
    stats.place(x=20, y=H - 132)

    def tick():
        eng = current_engine[0]
        now = time.time()
        st = eng.state
        done = eng.downloaded()
        total = eng.total
        dt = now - state["last_t"]
        if dt >= 0.5:
            inst = max(0, eng.session_bytes - state["last_bytes"]) / dt
            state["speed"] = inst if state["speed"] == 0 else state["speed"] * 0.6 + inst * 0.4
            state["last_bytes"], state["last_t"] = eng.session_bytes, now
            if st == "downloading":
                speeds.append(state["speed"])
                state["avg_sum"] += state["speed"]
                state["avg_n"] += 1
                state["peak"] = max(state["peak"], state["speed"])
            else:
                state["speed"] = 0.0
                speeds.append(0.0)
        speed = state["speed"] if st == "downloading" else 0
        pct = done * 100 / total if total else 0
        state["phase"] += 0.02

        color, label = ACCENT, "BAĞLANIYOR"
        if not eng.url:
            color, label = ACCENT, "HAZIR (BEKLİYOR)"
            pause_btn.configure_btn("Yeni İndirme", ACCENT, True)
            cancel_btn.configure_btn("Tepsiye Küçült", "#3a3f55", True)
        elif st == "downloading":
            color, label = ACCENT, "İNDİRİLİYOR"
            pause_btn.configure_btn("Duraklat", ACCENT, eng.resumable)
            cancel_btn.configure_btn("İptal", "#3a3f55", True)
        elif st == "paused":
            color, label = AMBER, "DURAKLATILDI"
            pause_btn.configure_btn("Devam Et", GREEN, True)
            cancel_btn.configure_btn("İptal", "#3a3f55", True)
        elif st == "error":
            color, label = RED, "HATA: " + (eng.error or "")[:40]
            pause_btn.configure_btn("Tekrar Dene", AMBER, True)
            cancel_btn.configure_btn("Kapat", "#3a3f55", True)
        elif st == "done":
            color, label = GREEN, "TAMAMLANDI"
            pct = 100
            if pause_btn.winfo_ismapped():
                pause_btn.pack_forget()
                cancel_btn.configure_btn("Kapat")
                folder_btn.pack(side="left")
                file_btn.pack(side="left", padx=10)
        elif st == "connecting":
            pause_btn.configure_btn("Duraklat", ACCENT, False)

        draw_header(color, label)
        draw_body(color, done, total, speed, pct)
        draw_stats(done, total, speed)
        root.title(
            f"{pct:.0f}% • {fmt_size(speed)}/s — ArtoDownloader" if st == "downloading" else "ArtoDownloader"
        )
        root.after(250, tick)

    tick()
    root.mainloop()

"""ArtoDownloader: IDM mantığıyla çok parçalı, duraklatılabilir indirici (tkinter arayüzlü)."""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

CHUNK = 64 * 1024
MIN_SPLIT = 1024 * 1024  # Bundan küçük kalan parça bölünmez
MAX_RETRY = 8


class Segment:
    def __init__(self, start, end, pos=None):
        self.start, self.end = start, end
        self.pos = start if pos is None else pos
        self.active = False


def set_sparse(f):
    """NTFS sparse bayrağı: uzak ofsete yazma, aradaki alanı senkron sıfırlamaz (büyük dosyada gecikmeyi önler)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        import msvcrt
        ret = ctypes.c_ulong()
        ctypes.windll.kernel32.DeviceIoControl(ctypes.c_void_p(msvcrt.get_osfhandle(f.fileno())),
                                               0x900C4, None, 0, None, 0, ctypes.byref(ret), None)
    except Exception:
        pass


def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "download"


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


class Engine:
    def __init__(self, url, dest_dir, headers, filename_hint="", connections=8):
        self.url, self.dest_dir = url, dest_dir
        self.headers = headers
        self.hint = filename_hint
        self.connections = connections
        self.total = 0
        self.resumable = False
        self.filename = ""
        self.etag = ""
        self.segs = []
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.cancelled = False
        self.error = None
        self.state = "connecting"  # connecting|downloading|paused|done|error|cancelled
        self.session_bytes = 0
        self.single_done = 0
        self._resps = set()
        self._sup = None
        self._first = None  # probe'dan kalan açık bağlantı

    # ---------- HTTP ----------
    def _open(self, rng=None, timeout=20):
        h = dict(self.headers)
        if rng:
            h["Range"] = rng
        resp = urllib.request.urlopen(urllib.request.Request(self.url, headers=h), timeout=timeout)
        with self.lock:
            self._resps.add(resp)
        return resp

    def _close(self, resp):
        with self.lock:
            self._resps.discard(resp)
        try:
            resp.close()
        except Exception:
            pass

    def probe(self):
        # Açık uçlu Range: bağlantı açık kalır ve ilk parça olarak kullanılır
        resp = None
        for attempt in range(4):  # takılan/düşen ilk bağlantıyı kısa timeout ile tekrar dene
            try:
                resp = self._open("bytes=0-", timeout=6 + attempt * 4)
                break
            except urllib.error.HTTPError:
                raise
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(0.3)
        try:
            self.url = resp.geturl()  # yönlendirmeler çözüldü
            info = resp.headers
            self.etag = info.get("ETag", "")
            if resp.status == 206:
                m = re.search(r"/(\d+)$", info.get("Content-Range", ""))
                if m:
                    self.total = int(m.group(1))
                    self.resumable = True
            else:
                self.total = int(info.get("Content-Length") or 0)
            name = self.hint
            cd = info.get("Content-Disposition", "")
            m = re.search(r"filename\*=(?:UTF-8|utf-8)''([^;]+)", cd)
            if m:
                name = urllib.parse.unquote(m.group(1))
            else:
                m = re.search(r'filename="?([^";]+)"?', cd)
                if m:
                    name = m.group(1)
            if not name:
                name = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(self.url).path))
            self.filename = safe_name(name)
            self._first = resp  # açık bırak
        except BaseException:
            self._close(resp)
            raise

    # ---------- Durum dosyası ----------
    def _paths(self):
        base = os.path.join(self.dest_dir, self.filename)
        return base, base + ".part", base + ".arto"

    def prepare(self):
        final, part, state = self._paths()
        if os.path.exists(part) and os.path.exists(state):
            try:
                st = json.load(open(state, encoding="utf-8"))
                if st["total"] == self.total and st["resumable"] == self.resumable and \
                        (not st.get("etag") or not self.etag or st["etag"] == self.etag):
                    self.segs = [Segment(*s) for s in st["segs"]]
                    if self._first is not None:  # devam: Range başlangıcı farklı
                        self._close(self._first)
                        self._first = None
                    return
            except Exception:
                pass
        if os.path.exists(final):  # çakışmayı önle
            stem, ext = os.path.splitext(self.filename)
            i = 1
            while os.path.exists(os.path.join(self.dest_dir, f"{stem} ({i}){ext}")):
                i += 1
            self.filename = f"{stem} ({i}){ext}"
            final, part, state = self._paths()
        with open(part, "wb") as f:
            if self.total:
                set_sparse(f)  # NTFS sparse: truncate ile önceden yer ayırmak 3.4GB için ~5sn sürüyordu; gerek yok
        if self.resumable and self.total:
            n = max(1, min(self.connections, self.total // MIN_SPLIT))
            size = self.total // n
            self.segs = [Segment(i * size, self.total - 1 if i == n - 1 else (i + 1) * size - 1)
                         for i in range(n)]
        else:
            self.segs = []

    def save_state(self):
        if not self.resumable:
            return
        _, _, state = self._paths()
        with self.lock:
            data = {"url": self.url, "total": self.total, "etag": self.etag,
                    "resumable": self.resumable,
                    "segs": [[s.start, s.end, s.pos] for s in self.segs]}
        tmp = state + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, state)

    # ---------- İlerleme ----------
    def downloaded(self):
        if not self.resumable:
            return self.single_done
        with self.lock:
            return sum(max(0, min(s.pos, s.end + 1) - s.start) for s in self.segs)

    # ---------- İş parçacıkları ----------
    def _next_segment(self):
        with self.lock:
            for s in self.segs:
                if not s.active and s.pos <= s.end:
                    s.active = True
                    return s
            # Dinamik bölme: en çok işi kalan parçanın ikinci yarısını al
            best, rem = None, 0
            for s in self.segs:
                r = s.end - s.pos + 1
                if s.active and r > rem:
                    best, rem = s, r
            if best and rem >= 2 * MIN_SPLIT:
                mid = best.pos + rem // 2
                new = Segment(mid, best.end)
                new.active = True
                best.end = mid - 1
                self.segs.append(new)
                return new
        return None

    def _download_segment(self, seg):
        _, part, _ = self._paths()
        fails = 0
        while not self.stop.is_set():
            with self.lock:
                if seg.pos > seg.end:
                    return
                pos, end = seg.pos, seg.end
            resp = None
            try:
                if seg.start == 0 and pos == 0:
                    with self.lock:  # probe bağlantısını yeniden kullan, yeni bağlantı kurma
                        resp, self._first = self._first, None
                if resp is None:
                    resp = self._open(f"bytes={pos}-{end}", timeout=15)
                if resp.status != 206:
                    raise IOError(f"Sunucu Range desteklemedi ({resp.status})")
                with open(part, "r+b", buffering=0) as fh:
                    while True:
                        with self.lock:
                            rem = seg.end - seg.pos + 1
                            cur = seg.pos
                        if rem <= 0:
                            return
                        if self.stop.is_set():
                            return
                        data = resp.read(min(CHUNK, rem))
                        if not data:
                            raise IOError("Bağlantı erken kapandı")
                        fh.seek(cur)
                        fh.write(data)
                        with self.lock:
                            seg.pos = cur + len(data)
                            self.session_bytes += len(data)
                        fails = 0
            except Exception as e:
                if self.stop.is_set():
                    return
                fails += 1
                if fails > MAX_RETRY:
                    raise
                time.sleep(min(2 * fails, 10))
            finally:
                if resp:
                    self._close(resp)

    def _worker(self):
        try:
            while not self.stop.is_set():
                seg = self._next_segment()
                if seg is None:
                    return
                try:
                    self._download_segment(seg)
                finally:
                    with self.lock:
                        seg.active = False
        except Exception as e:
            self.error = str(e)
            self.stop.set()

    def _single(self):
        _, part, _ = self._paths()
        try:
            with self.lock:
                resp, self._first = self._first, None
            if resp is None:
                resp = self._open(timeout=30)
            with open(part, "wb") as fh:
                while not self.stop.is_set():
                    data = resp.read(CHUNK)
                    if not data:
                        break
                    fh.write(data)
                    with self.lock:
                        self.single_done += len(data)
                        self.session_bytes += len(data)
                else:
                    return
            self._close(resp)
        except Exception as e:
            if not self.stop.is_set():
                self.error = str(e)
                self.stop.set()

    def _supervise(self):
        self.state = "downloading"
        if self.resumable:
            threads = [threading.Thread(target=self._worker, daemon=True)
                       for _ in range(self.connections)]
        else:
            threads = [threading.Thread(target=self._single, daemon=True)]
        for t in threads:
            t.start()
        last = time.time()
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
            if time.time() - last > 2:
                self.save_state()
                last = time.time()
        for t in threads:
            t.join()
        final, part, state = self._paths()
        if self.cancelled:
            for p in (part, state):
                if os.path.exists(p):
                    os.remove(p)
            self.state = "cancelled"
        elif self.error:
            self.save_state()
            self.state = "error"
        elif self.stop.is_set():
            self.save_state()
            self.state = "paused"
        else:
            if self.resumable and any(s.pos <= s.end for s in self.segs):
                self.error = "İndirme eksik kaldı"
                self.state = "error"
                return
            os.replace(part, final)
            if os.path.exists(state):
                os.remove(state)
            self.state = "done"

    # ---------- Kontrol ----------
    def start(self):
        self.stop.clear()
        self.error = None
        self.state = "downloading"
        self._sup = threading.Thread(target=self._supervise, daemon=True)
        self._sup.start()

    def _kill_connections(self):
        self.stop.set()
        with self.lock:
            resps = list(self._resps)
        for r in resps:
            try:
                r.close()
            except Exception:
                pass

    def pause(self):
        if self.resumable:
            self._kill_connections()

    def cancel(self):
        self.cancelled = True
        self._kill_connections()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="")
    p.add_argument("--referer", default="")
    p.add_argument("--cookie", default="")
    p.add_argument("--ua", default="")
    p.add_argument("--filename", default="")
    p.add_argument("--dir", default="")
    p.add_argument("--connections", type=int, default=8)
    args = p.parse_args()
    from ui import run_gui
    run_gui(args, Engine, fmt_size)


if __name__ == "__main__":
    main()

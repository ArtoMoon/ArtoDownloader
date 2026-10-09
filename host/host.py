"""ArtoDownloader Native Messaging Host."""
import json
import os
import socket
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
IPC_PORT = 58432

if os.name == "nt":
    import msvcrt
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)


def log(msg):
    try:
        logdir = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "ArtoDownloader")
        os.makedirs(logdir, exist_ok=True)
        with open(os.path.join(logdir, "host.log"), "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def read_bytes(n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sys.stdin.buffer.read(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


def read_message():
    raw = read_bytes(4)
    if len(raw) < 4:
        return None
    length = struct.unpack("=I", raw)[0]
    if length > 10 * 1024 * 1024:
        raise ValueError(f"Mesaj çok büyük: {length} bayt")
    body = read_bytes(length)
    if len(body) < length:
        raise ValueError("Eksik mesaj gövdesi")
    return json.loads(body.decode("utf-8"))


def send_message(obj):
    data = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def try_send_to_running_instance(msg):
    """Zaten açık olan ArtoDownloader varsa yerel soket üzerinden haberdar et."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(("127.0.0.1", IPC_PORT))
            payload = json.dumps(msg).encode("utf-8")
            s.sendall(struct.pack("=I", len(payload)) + payload)
            res_raw = s.recv(4)
            if len(res_raw) == 4:
                rlen = struct.unpack("=I", res_raw)[0]
                s.recv(rlen)
            return True
    except Exception:
        return False


def launch(msg):
    url = msg.get("url", "")
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("Geçersiz URL")

    # 1. Önce tepside/arka planda çalışan ArtoDownloader'a gönder
    if try_send_to_running_instance(msg):
        log(f"Çalışan ArtoDownloader'a iletildi: {url}")
        return

    # 2. Çalışmıyorsa yeni süreç başlat
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.dirname(sys.executable))
        cmd = [os.path.join(base, "ArtoDownloader", "ArtoDownloader.exe")]
    else:
        python = sys.executable
        pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
        if os.name == "nt" and os.path.exists(pythonw):
            python = pythonw
        cmd = [python, os.path.join(HERE, "app.py")]

    cmd += [
        "--url", url,
        "--referer", msg.get("referrer", ""),
        "--cookie", msg.get("cookie", ""),
        "--ua", msg.get("userAgent", ""),
        "--filename", msg.get("filename", "")
    ]

    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True
    )
    log(f"Yeni süreç başlatıldı: {url}")


def main():
    try:
        msg = read_message()
        if msg is None:
            return
        launch(msg)
        send_message({"ok": True})
    except Exception as e:
        log(f"HATA: {e!r}")
        send_message({"ok": False, "error": str(e)})


if __name__ == "__main__":
    main()

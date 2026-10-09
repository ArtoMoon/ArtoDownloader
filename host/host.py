"""Native messaging host: eklentiden gelen mesajı alır ve indirme uygulamasını başlatır."""
import json
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

if os.name == "nt":
    import msvcrt
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)


def read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    length = struct.unpack("=I", raw)[0]
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def send_message(obj):
    data = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def launch(msg):
    url = msg.get("url", "")
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("Geçersiz URL")

    if getattr(sys, "frozen", False):
        # Kurulu düzen: {app}\ArtoHost\ArtoHost.exe  ->  {app}\ArtoDownloader\ArtoDownloader.exe
        base = os.path.dirname(os.path.dirname(sys.executable))
        cmd = [os.path.join(base, "ArtoDownloader", "ArtoDownloader.exe")]
    else:
        python = sys.executable
        pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
        if os.name == "nt" and os.path.exists(pythonw):
            python = pythonw
        cmd = [python, os.path.join(HERE, "app.py")]

    cmd += ["--url", url,
            "--referer", msg.get("referrer", ""),
            "--cookie", msg.get("cookie", ""),
            "--ua", msg.get("userAgent", ""),
            "--filename", msg.get("filename", "")]

    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)


def main():
    try:
        msg = read_message()
        if msg is None:
            return
        launch(msg)
        send_message({"ok": True})
    except Exception as e:  # noqa
        logdir = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "ArtoDownloader")
        os.makedirs(logdir, exist_ok=True)
        with open(os.path.join(logdir, "host.log"), "a", encoding="utf-8") as f:
            f.write(f"{e!r}\n")
        send_message({"ok": False, "error": str(e)})


if __name__ == "__main__":
    main()

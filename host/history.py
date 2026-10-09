"""ArtoDownloader İndirme Geçmişi ve Durum Yöneticisi."""
import json
import os
import time

HISTORY_FILE = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "ArtoDownloader",
    "history.json"
)


class HistoryManager:
    def __init__(self):
        self.file_path = HISTORY_FILE
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self.items = self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception:
                pass
        return []

    def save(self):
        try:
            tmp = self.file_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.file_path)
        except Exception:
            pass

    def add(self, item):
        # Başa ekle
        self.items.insert(0, item)
        self.save()
        return item

    def update(self, item_id, **kwargs):
        for it in self.items:
            if it.get("id") == item_id:
                it.update(kwargs)
                break
        self.save()

    def remove(self, item_id, delete_file=False):
        target = None
        for it in self.items:
            if it.get("id") == item_id:
                target = it
                break
        if target:
            if delete_file:
                fp = target.get("filepath")
                if fp and os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
                part = fp + ".part" if fp else None
                if part and os.path.exists(part):
                    try:
                        os.remove(part)
                    except Exception:
                        pass
                state = fp + ".arto" if fp else None
                if state and os.path.exists(state):
                    try:
                        os.remove(state)
                    except Exception:
                        pass
            self.items.remove(target)
            self.save()

    def clear_completed(self):
        self.items = [it for it in self.items if it.get("status") != "done"]
        self.save()

"""Local JSON state, atomically replaced and never served as static content."""
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4


class SessionStore:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = RLock()

    def _read(self, name, default):
        path = self.root / name
        if not path.exists():
            return copy.deepcopy(default)
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, name, value):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / name
        temp = path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)

    @staticmethod
    def _filename(session_id):
        if len(session_id) != 32 or any(c not in "0123456789abcdef" for c in session_id):
            raise KeyError(session_id)
        return f"session-{session_id}.json"

    def create(self):
        with self.lock:
            item = {"id": uuid4().hex, "title": "New conversation", "messages": [],
                    "updated_at": datetime.now(timezone.utc).isoformat()}
            self._write(self._filename(item["id"]), item)
            return item

    def get(self, session_id):
        with self.lock:
            item = self._read(self._filename(session_id), None)
            if item is None:
                raise KeyError(session_id)
            return item

    def list_sessions(self):
        with self.lock:
            items = [self._read(p.name, {}) for p in self.root.glob("session-*.json")]
            return sorted([{k: item[k] for k in ("id", "title", "updated_at")}
                           for item in items], key=lambda item: item["updated_at"], reverse=True)

    def append_turn(self, session_id, prompt, reply, status="complete", kind="assistant", metrics=None):
        with self.lock:
            item = self.get(session_id)
            if not item["messages"]:
                item["title"] = prompt[:64]
            item["messages"].extend([
                {"role": "user", "content": prompt, "status": status},
                {"role": "assistant", "content": reply, "status": status,
                 "kind": kind, "metrics": metrics or {}},
            ])
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write(self._filename(session_id), item)

    def delete(self, session_id):
        with self.lock:
            self.get(session_id)
            (self.root / self._filename(session_id)).unlink()

    def memories(self):
        with self.lock:
            return self._read("memories.json", [])

    def remember(self, content):
        with self.lock:
            items = self.memories()
            for item in items:
                if item["content"] == content:
                    return item
            if len(items) >= 100:
                raise ValueError("Memory is full. Forget an item before adding another.")
            item = {"id": uuid4().hex, "content": content}
            items.append(item)
            self._write("memories.json", items)
            return item

    def forget(self, memory_id):
        with self.lock:
            items = self.memories()
            remaining = [item for item in items if item["id"] != memory_id]
            if len(remaining) == len(items):
                raise KeyError(memory_id)
            self._write("memories.json", remaining)

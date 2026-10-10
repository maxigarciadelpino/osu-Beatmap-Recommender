import threading
from . import config as C
from .api import api_get


class Poller(threading.Thread):
    def __init__(self, tm, uid, store, session_id, since_iso, on_new, log=print):
        super().__init__(daemon=True)
        self.tm, self.uid, self.store = tm, uid, store
        self.session_id, self.since, self.on_new, self.log = session_id, since_iso, on_new, log
        self.stop_flag = threading.Event()

    def stop(self):
        self.stop_flag.set()

    def run(self):
        while not self.stop_flag.is_set():
            try:
                scores = api_get(f"{C.BASE}/users/{self.uid}/scores/recent", self.tm,
                                 {"mode": "osu", "include_fails": 1, "limit": 50}) or []
                fresh = [s for s in reversed(scores) if s["ended_at"] >= self.since]
                new = [s for s in fresh if self.store.add_play(s, self.session_id)]
                if new and not self.stop_flag.is_set():
                    self.on_new(new)
            except Exception as e:
                self.log(f"Poller: {e}")
            self.stop_flag.wait(C.POLL_INTERVAL)

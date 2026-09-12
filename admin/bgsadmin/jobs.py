"""Work that outlives one request, such as a video transcode or a push.

Each job runs on its own thread; the UI polls GET jobs/<id> for its state.
Nothing is kept across a restart. A job's function gets a `log` callable for
short lines the UI may show, and returns JSON data as its result. An
exception marks the job failed: an ApiError keeps its code and message,
anything else is reported plainly and printed to the server's terminal.
"""
import secrets
import threading
import time
import traceback

from .errors import ApiError

KEEP = 50                      # finished jobs remembered for polling

_LOCK = threading.Lock()
_JOBS = {}


class Job:
    def __init__(self, kind):
        self.id = secrets.token_hex(8)
        self.kind = kind
        self.state = "queued"
        self.lines = []
        self.result = None
        self.error = None
        self.created = time.time()
        self.finished = None

    def log(self, line):
        self.lines.append(str(line)[:500])
        del self.lines[:-200]

    def view(self):
        return {"id": self.id, "kind": self.kind, "state": self.state, "log_tail": self.lines[-20:],
                "result": self.result, "error": self.error, "created": self.created, "finished": self.finished}


def start(kind, fn):
    """Run fn(log) on a new thread; returns the Job at once."""
    job = Job(kind)

    def run():
        job.state = "running"
        try:
            job.result = fn(job.log)
            job.state = "done"
        except ApiError as e:
            job.error = e.body().get("error")
            job.state = "failed"
        except Exception:
            traceback.print_exc()
            job.error = {"code": "internal", "message": "The job stopped with an error. The server's terminal has the details."}
            job.state = "failed"
        finally:
            job.finished = time.time()

    with _LOCK:
        _JOBS[job.id] = job
        done = sorted((j for j in _JOBS.values() if j.finished), key=lambda j: j.finished)
        for old in done[:max(0, len(_JOBS) - KEEP)]:
            del _JOBS[old.id]
    threading.Thread(target=run, name="job-" + kind, daemon=True).start()
    return job


def get(job_id):
    with _LOCK:
        return _JOBS.get(job_id)


def running(kind=None):
    """Jobs still queued or running, optionally of one kind."""
    with _LOCK:
        return [j for j in _JOBS.values() if j.state in ("queued", "running") and (kind is None or j.kind == kind)]

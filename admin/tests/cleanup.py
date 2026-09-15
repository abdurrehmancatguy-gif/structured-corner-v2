"""Exit nets for the admin's tests: however a test run ends, the admin
servers and the PostgreSQL clusters it started stop, and their folders go.

    import cleanup
    cleanup.on_exit(fn)          # run fn when this process ends, however it ends
    cleanup.forget(fn)           # fn has done its work already (a Box closed normally)
    w = cleanup.watchdog(*cmd)   # run cmd once this process is gone, even after SIGKILL
    cleanup.stop(w)              # that watchdog is no longer needed

Three nets, because each alone leaves something behind:
1. atexit, for a normal end or an uncaught exception;
2. a handler for SIGTERM, SIGHUP and SIGALRM, which Python dies of without
   running atexit. SIGALRM is what the 110 s alarm the test commands run
   under sends (perl -e 'alarm shift; exec @ARGV' 110 ...). The handler runs
   the cleanups, then dies of the same signal;
3. a watchdog: a shell in a session of its own that waits for this process
   to end and then runs its command, for the SIGKILL nothing can catch.
"""
import atexit
import os
import signal
import subprocess

_cleanups = []


def on_exit(fn):
    """Run fn when the process ends, however it ends (short of SIGKILL)."""
    _cleanups.append(fn)
    return fn


def forget(fn):
    while fn in _cleanups:
        _cleanups.remove(fn)


def run_cleanups():
    """Every cleanup still registered, newest first; one that fails does not
    stop the others."""
    while _cleanups:
        fn = _cleanups.pop()
        try:
            fn()
        except Exception:
            pass


def _on_signal(signum, _frame):
    run_cleanups()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


atexit.register(run_cleanups)
for _s in (signal.SIGTERM, signal.SIGHUP, signal.SIGALRM):
    if signal.getsignal(_s) in (signal.SIG_DFL, None):
        signal.signal(_s, _on_signal)

# $1 is the process to outlive; the rest is the command.
WATCH = 'while kill -0 "$1" 2>/dev/null; do sleep 1; done; shift; exec "$@"'


def watchdog(*cmd):
    """Run cmd once this process has ended, however it ended. Returns the
    watchdog's Popen, for stop() once what it guards is cleaned up."""
    return subprocess.Popen(["/bin/sh", "-c", WATCH, "bgs-watchdog", str(os.getpid())] + [str(c) for c in cmd],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)


def stop(proc):
    """Stop a watchdog whose work is done. None does nothing."""
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)

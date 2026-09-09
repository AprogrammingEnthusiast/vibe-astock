"""Independent deadline survives a backend crash (first release: macOS/Linux)."""
import os
import json
import signal
import subprocess
import sys
import time


def main() -> int:
    timeout = float(sys.argv[1])
    parent = int(sys.argv[2])
    if os.getppid() != parent:
        return 1
    reap_group = sys.argv[3] == "--bridge-reap-group"
    child = subprocess.Popen(sys.argv[4:] if reap_group else sys.argv[3:])
    deadline = time.monotonic() + timeout
    while child.poll() is None:
        if time.monotonic() > deadline or os.getppid() != parent:
            os.killpg(os.getpgrp(), signal.SIGKILL)
        time.sleep(.2)
    if reap_group:
        # A private bridge result is followed by the child's actual exit status.
        # The owner waits for our death before accepting it. Always reap the
        # entire group, even if EOF made Node exit before we noticed parent death.
        try:
            print(json.dumps({"type": "bridge_exit", "code": child.returncode}), flush=True)
        finally:
            os.killpg(os.getpgrp(), signal.SIGKILL)
    if os.getppid() != parent:
        os.killpg(os.getpgrp(), signal.SIGKILL)
    return child.returncode


if __name__ == "__main__":
    raise SystemExit(main())

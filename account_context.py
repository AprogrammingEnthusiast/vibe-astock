"""Server-selected account context for the shared, single-process application."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from pathlib import Path
import os
import re
import threading
from types import SimpleNamespace

ENABLED = os.environ.get("VIBE_SHARED_APP") == "1"
_account = ContextVar("website_account", default=None)
_states = {}
_lock = threading.RLock()


def current():
    return _account.get()


@contextmanager
def bind(user: dict, root: Path):
    if not re.fullmatch(r"[0-9a-f]{32}", user["id"]):
        raise ValueError("Invalid server account ID")
    home = root / user["id"]
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    if home.is_symlink() or home.resolve().parent != root.resolve():
        raise ValueError("Invalid account directory")
    token = _account.set({**user, "home": home})
    try:
        yield
    finally:
        _account.reset(token)


def home() -> Path:
    account = current()
    if account:
        return account["home"]
    if ENABLED:
        raise RuntimeError("Private operation requires an authenticated account")
    return Path.home()


def path(default):
    """Resolve existing data paths inside the authenticated account's home."""
    if not ENABLED:
        return default
    value = Path(default).expanduser()
    private_home = home()
    if value.is_relative_to(private_home):
        return default
    roots = [(os.environ.get(key), relative) for key, relative in (
        ("VR_REPORTS_DIR", ".vibe-research/myreports"),
        ("VR_DATA_DIR", ".vibe-research"),
        ("ASTOCK_AGENT_HOME", ".vibe-astock-agent"),
        ("CODEX_HOME", ".codex"))]
    roots.append((str(Path.home()), ""))
    for base, relative in roots:
        if base and value.is_relative_to(Path(base).expanduser()):
            result = private_home / relative / value.relative_to(Path(base).expanduser())
            return str(result) if isinstance(default, str) else result
    raise RuntimeError("Private data path is outside configured data roots")


def thread(*args, target=None, **kwargs):
    """Explicitly carry identity into application-owned background threads."""
    if current() is None:
        return threading.Thread(*args, target=target, **kwargs)
    context = copy_context()
    arguments = kwargs.pop("args", ())
    keywords = kwargs.pop("kwargs", {})
    return threading.Thread(*args, target=lambda: context.run(target, *arguments, **keywords), **kwargs)


def state(module, factory):
    if not ENABLED:
        return module
    account = current()
    if account is None:
        raise RuntimeError("Private state requires an authenticated account")
    key = (str(account["home"]), module.__name__)
    with _lock:
        if key not in _states:
            _states[key] = SimpleNamespace(**factory())
        return _states[key]

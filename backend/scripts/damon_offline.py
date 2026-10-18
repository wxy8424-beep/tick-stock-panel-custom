"""Offline-only bootstrap. Run directly; never import into a running application."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ACTIVE_SANDBOX = None
if __name__ == "__main__":
    sys.modules["damon_offline"] = sys.modules[__name__]


class Sandbox:
    """Fresh process, temporary filesystem, ASGI only; not an OS/native-code sandbox."""

    def __enter__(self):
        global ACTIVE_SANDBOX
        if any(name == "app" or name.startswith("app.") for name in sys.modules):
            raise RuntimeError("fresh_process_required")
        self.temp = tempfile.TemporaryDirectory(prefix="damon-offline-")
        self.root = Path(self.temp.name).resolve()
        self.writes: set[str] = set()
        self.denied: list[str] = []
        self.runner = None
        try:
            # Only non-secret OS loader variables survive. Never load a repository .env.
            inherited = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "PATH")
                         if k in os.environ}
            os.environ.clear()
            os.environ.update(inherited)
            os.environ.update(DATA_DIR=str(self.root / "data"),
                              TICKFLOW_ENV_FILE=str(self.root / "isolated.env"),
                              TEMP=str(self.root), TMP=str(self.root), HOME=str(self.root),
                              USERPROFILE=str(self.root), AI_API_KEY="", TICKFLOW_API_KEY="",
                              AUTH_PASSWORD="", WEB_CONCURRENCY="1", PYTHONDONTWRITEBYTECODE="1")
            sys.dont_write_bytecode = True
            (self.root / "isolated.env").write_text("", encoding="utf-8")
            self.writes.add(str(self.root / "isolated.env"))
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            # Windows may build an internal loopback socketpair when creating its
            # event loop. Do that before installing the no-network application guard.
            import asyncio
            self.runner = asyncio.Runner()
            self.runner.get_loop()
            self._install_guards()
            ACTIVE_SANDBOX = self
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _install_guards(self):
        import importlib.abc

        blocked = ("app.main", "app.backtest", "app.jobs", "app.data_providers",
                   "app.tickflow.repository", "app.tickflow.policy", "app.custom.assistant",
                   "app.services.quote_service", "app.services.depth_service",
                   "app.services.minute_refresh", "app.services.ext_pull",
                   "app.services.financial_sync", "app.services.data_integrity")

        class NoBusinessImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if any(fullname == p or fullname.startswith(p + ".") for p in blocked):
                    raise ImportError("business_module_forbidden")
                return None

        self.blocked_imports = blocked
        sys.meta_path.insert(0, NoBusinessImports())

        def inside(path):
            return path == self.root or self.root in path.parents

        def audit(event, args):
            if event in {"socket.connect", "socket.bind", "socket.getaddrinfo",
                         "subprocess.Popen", "os.system", "os.posix_spawn", "sqlite3.connect"}:
                self.denied.append(event)
                raise PermissionError("offline_operation_forbidden")
            paths = []
            if event == "open" and not isinstance(args[0], int):
                path = Path(os.fsdecode(args[0])).resolve()
                mode, flags = args[1], args[2]
                writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                    isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
                if writing:
                    paths.append(path)
                elif not inside(path) and (path.name.casefold().startswith(".env")
                                         or path.name.casefold() in {"auth.json", "secrets.json"}
                                         or "data" in {part.casefold() for part in path.parts}):
                    self.denied.append("credential_or_data_read")
                    raise PermissionError("outside_data_read_forbidden")
            elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.truncate"}:
                if not isinstance(args[0], int):
                    paths.append(Path(os.fsdecode(args[0])).resolve())
            elif event in {"os.rename", "os.link", "os.symlink"}:
                paths.extend(Path(os.fsdecode(p)).resolve() for p in args[:2])
            for path in paths:
                if not inside(path):
                    self.denied.append("outside_write")
                    raise PermissionError("outside_write_forbidden")
                self.writes.add(str(path))

        sys.addaudithook(audit)

    def run(self, coroutine):
        return self.runner.run(coroutine)

    def __exit__(self, *_):
        global ACTIVE_SANDBOX
        try:
            if self.runner is not None:
                self.runner.close()
        finally:
            ACTIVE_SANDBOX = None
            self.temp.cleanup()


def main():
    import json

    if len(sys.argv) != 1:
        raise SystemExit("ASGI only: no listener, endpoint or credential arguments accepted")
    with Sandbox() as sandbox:
        from damon_offline_app import demo
        result = sandbox.run(demo())
        result.update(root=str(sandbox.root), writes=sorted(sandbox.writes))
    result["cleaned"] = not sandbox.root.exists()
    print(json.dumps(result))


if __name__ == "__main__":
    main()

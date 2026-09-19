"""Shared helpers for the sudo-request test suite.

Everything runs against isolated temp dirs (runtime socket, config) plus
the fake-sudo fixture, so the real user daemon/config/sudo are untouched.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "sudo-request")
FIXTURE_SUDO = os.path.join(REPO, "tests", "fixtures", "fake-sudo")


def load_script():
    """Import the sudo-request file as a module without running main()."""
    mod = types.ModuleType("sudo_request_under_test")
    with open(SCRIPT, encoding="utf-8") as fh:
        src = fh.read()
    exec(compile(src, SCRIPT, "exec"), mod.__dict__)
    return mod


def make_env(tmp, extra=None):
    """Isolated environment: temp runtime/config dirs, fake-sudo first."""
    rt = os.path.join(tmp, "rt")
    cfg = os.path.join(tmp, "cfg")
    bindir = os.path.join(tmp, "bin")
    os.makedirs(rt)
    os.makedirs(os.path.join(cfg, "sudo-request"))
    os.makedirs(bindir)
    shutil.copy(FIXTURE_SUDO, os.path.join(bindir, "sudo"))
    os.chmod(os.path.join(bindir, "sudo"), 0o755)
    env = dict(os.environ)
    env["XDG_RUNTIME_DIR"] = rt
    env["XDG_CONFIG_HOME"] = cfg
    env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    if extra:
        env.update(extra)
    return env, rt, cfg


def write_config(cfgdir, mapping):
    with open(os.path.join(cfgdir, "sudo-request", "config.json"),
              "w", encoding="utf-8") as fh:
        json.dump(mapping, fh)


def base_config(**overrides):
    cfg = {
        "keep_sudo": False,
        "auto_accept": True,
        "keepalive_interval": 60,
        "confirm_timeout": 30,
        "terminal": None,
        "audit_log": None,
    }
    cfg.update(overrides)
    return cfg


def wait_for_socket(sock, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(sock):
            return True
        time.sleep(0.1)
    return False


class DaemonCase:
    """Mixin: start/stop a real daemon bound to temp dirs.

    The daemon token is read from the loaded module so the value itself
    stays out of docs and shells.
    """

    mod = None
    env = None
    tmp = None
    daemon = None
    daemon_log = None

    def start_daemon(self, config=None, stdin=None, extra_env=None):
        # Restart-safe: tear down any previous instance first.
        self.stop_daemon()
        if self.tmp is not None:
            shutil.rmtree(self.tmp, ignore_errors=True)
        self.mod = load_script()
        self.tmp = tempfile.mkdtemp(prefix="sr-test-")
        self.env, rt, cfgdir = make_env(self.tmp, extra_env)
        resolved = {}
        for key, value in (config or {}).items():
            if isinstance(value, str):
                value = value.replace("{TMP}", self.tmp)
            resolved[key] = value
        write_config(cfgdir, base_config(**resolved))
        self.daemon_log = open(os.path.join(self.tmp, "daemon.log"),
                               "w", encoding="utf-8")
        self.daemon = subprocess.Popen(
            [sys.executable, SCRIPT, self.mod._DAEMON_TOKEN],
            stdin=stdin or subprocess.DEVNULL,
            stdout=self.daemon_log, stderr=subprocess.STDOUT,
            env=self.env)
        sock = os.path.join(rt, "sudo-request.sock")
        self.assertTrue(wait_for_socket(sock),
                        "daemon did not bind its socket in time")
        # Give the daemon a beat to finish startup past the bind.
        time.sleep(0.5)
        return sock

    def run_client(self, *args, input=None, timeout=20, cwd=None,
                   extra_env=None):
        env = dict(self.env)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, cwd=cwd, env=env)

    def stop_daemon(self):
        if self.daemon is not None:
            self.daemon.terminate()
            try:
                self.daemon.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.daemon.kill()
                self.daemon.wait()
            self.daemon = None
        if self.daemon_log is not None:
            self.daemon_log.close()
            self.daemon_log = None

    def daemon_log_text(self):
        with open(os.path.join(self.tmp, "daemon.log"),
                  encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def tearDown(self):
        self.stop_daemon()
        if self.tmp is not None:
            shutil.rmtree(self.tmp, ignore_errors=True)
            self.tmp = None

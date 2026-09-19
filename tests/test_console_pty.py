"""Fake-terminal tests: the daemon console driven through a pty pair.

The master end plays the user (keypresses, no Enter); the slave end is
the daemon's stdin, so cbreak mode engages exactly like in a real
terminal window.
"""

import contextlib
import io
import os
import pty
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import load_script

mod = load_script()


class PtyConsole:
    """Daemon Console with stdin attached to a pty slave."""

    def __init__(self, test):
        self._mfd, sfd = pty.openpty()
        self._slave = os.fdopen(sfd, "r")
        self._old_stdin = sys.stdin
        sys.stdin = self._slave
        # Isolated config: toggles save back, never touching ~/.config.
        self._cfgdir = tempfile.mkdtemp(prefix="sr-pty-cfg-")
        self._old_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._cfgdir
        # Silence the chatty console prints for clean test output.
        self._redir = contextlib.redirect_stdout(io.StringIO())
        self._redir.__enter__()
        self.daemon = mod.Daemon(dict(mod.DEFAULT_CONFIG))
        self.daemon.console.start()
        assert self.daemon.console._instant, "cbreak did not engage on pty"
        time.sleep(0.3)

    def press(self, data: bytes, settle=0.5):
        os.write(self._mfd, data)
        time.sleep(settle)

    def close(self):
        # Stop the input thread first so it can't steal the next stdin.
        self.daemon.console.stop()
        os.close(self._mfd)
        self._slave.close()
        self._redir.__exit__(None, None, None)
        sys.stdin = self._old_stdin
        if self._old_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._old_xdg
        shutil.rmtree(self._cfgdir, ignore_errors=True)


class InstantKeyTest(unittest.TestCase):
    def setUp(self):
        self.con = PtyConsole(self)

    def tearDown(self):
        self.con.close()

    def test_toggle_without_enter(self):
        d = self.con.daemon
        self.assertFalse(d.auto_accept)
        self.con.press(b"a")
        self.assertTrue(d.auto_accept)

    def test_toggles_never_touch_config(self):
        # Toggles are for this run only: no config file may be created
        # or modified by them. Permanent changes mean editing the JSON
        # (or deleting it for a fresh first-run setup).
        cfgfile = os.path.join(self.con._cfgdir, "sudo-request",
                               "config.json")
        self.assertFalse(os.path.exists(cfgfile))
        self.con.press(b"a")
        self.con.press(b"s")
        self.assertTrue(self.con.daemon.auto_accept)
        self.assertFalse(os.path.exists(cfgfile))

    def test_status_without_enter(self):
        # 's' prints settings and changes nothing.
        d = self.con.daemon
        before = (d.keep_sudo, d.auto_accept)
        self.con.press(b"s")
        self.assertEqual((d.keep_sudo, d.auto_accept), before)

    def test_answer_without_enter(self):
        out = {}
        t = threading.Thread(
            target=lambda: out.update(
                ans=self.con.daemon.console.confirm("0001", "cmd", 5.0)))
        t.start()
        time.sleep(0.5)
        self.con.press(b"y")
        t.join(timeout=5)
        self.assertIs(out.get("ans"), True)

    def test_enter_denies(self):
        out = {}
        t = threading.Thread(
            target=lambda: out.update(
                ans=self.con.daemon.console.confirm("0002", "cmd", 5.0)))
        t.start()
        time.sleep(0.5)
        self.con.press(b"\r")
        t.join(timeout=5)
        self.assertIs(out.get("ans"), False)

    def test_escape_burst_swallowed(self):
        self.con.press(b"\x1b[A")
        out = {}
        t = threading.Thread(
            target=lambda: out.update(
                ans=self.con.daemon.console.confirm("0003", "cmd", 5.0)))
        t.start()
        time.sleep(0.5)
        self.assertEqual(self.con.daemon.console._responses.qsize(), 0)
        self.con.press(b"y")
        t.join(timeout=5)
        self.assertIs(out.get("ans"), True)

    def test_stale_answer_drained(self):
        self.con.daemon.console._responses.put("y")  # leftover
        ans = self.con.daemon.console._ask("prompt? ", 0.3)
        self.assertEqual(ans, "")

    def test_toggle_then_answer_no_pollution(self):
        # The original line-buffering bug: 'a' + 'y' merged into "ay".
        out = {}
        self.con.press(b"a")  # fires instantly, nothing buffers
        t = threading.Thread(
            target=lambda: out.update(
                ans=self.con.daemon.console.confirm("0004", "cmd", 5.0)))
        t.start()
        time.sleep(0.5)
        self.con.press(b"y")
        t.join(timeout=5)
        self.assertIs(out.get("ans"), True)


if __name__ == "__main__":
    unittest.main()

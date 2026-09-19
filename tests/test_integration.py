"""End-to-end tests with the fake-sudo fixture.

A real daemon (temp socket/config) serves real client processes; the
fake `sudo` on PATH pretends the timestamp is valid, so no password is
needed. Covers stdout/stderr/exit codes/stdin, cwd isolation, the audit
log, timeout-deny, and the sudo-password path (proving the daemon never
steals password keystrokes from sudo).
"""

import json
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import DaemonCase, base_config


class RoundtripTest(DaemonCase, unittest.TestCase):
    def setUp(self):
        self.start_daemon()

    def test_echo_delegated_and_sudo(self):
        out = self.run_client("-u", "echo", "hello")
        self.assertEqual((out.returncode, out.stdout), (0, b"hello\n"))
        out = self.run_client("echo", "hello-sudo")
        self.assertEqual((out.returncode, out.stdout), (0, b"hello-sudo\n"))

    def test_exit_code_and_stderr(self):
        out = self.run_client("-u", "sh", "-c", "echo to-err >&2; exit 42")
        self.assertEqual(out.returncode, 42)
        self.assertEqual(out.stderr, b"to-err\n")

    def test_stdin_pipe(self):
        out = self.run_client("-u", "cat", input=b"piped-data\n")
        self.assertEqual((out.returncode, out.stdout), (0, b"piped-data\n"))

    def test_passthrough_dash_command(self):
        out = self.run_client("-p", "echo", "fine")
        self.assertEqual(out.stdout, b"fine\n")

    def test_concurrent_cwd_isolation(self):
        da = os.path.join(self.tmp, "cwda")
        db = os.path.join(self.tmp, "cwdb")
        os.makedirs(da)
        os.makedirs(db)
        for _ in range(3):
            results = {}
            threads = [
                threading.Thread(
                    target=lambda d, k: results.update(
                        {k: self.run_client("-u", "pwd", cwd=d)}),
                    args=(d, k))
                for d, k in ((da, "a"), (db, "b"))
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=20)
            self.assertEqual(results["a"].stdout.strip(), os.fsencode(da))
            self.assertEqual(results["b"].stdout.strip(), os.fsencode(db))


class AuditLogTest(DaemonCase, unittest.TestCase):
    def audit_file(self):
        return os.path.join(self.tmp, "audit.jsonl")

    def read_audit(self):
        with open(self.audit_file(), encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]

    def setUp(self):
        self.start_daemon({"audit_log": "{TMP}/audit.jsonl"})

    def test_entry_fields_and_defaults(self):
        out = self.run_client("-u", "echo", "hi")
        self.assertEqual(out.returncode, 0)
        entries = self.read_audit()
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["command"], ["echo", "hi"])
        self.assertEqual(e["decision"], "auto-accepted")
        self.assertEqual(e["exit"], 0)
        self.assertEqual(e["mode"], "delegated")
        self.assertIn("uid", e)
        self.assertIn("env", e)
        # Output is off by default so the log can't fill up fast.
        self.assertNotIn("stdout", e)
        self.assertNotIn("stderr", e)

    def test_stdin_captured(self):
        self.run_client("-u", "cat", input=b"logged-input\n")
        entries = self.read_audit()
        self.assertEqual(entries[-1]["stdin"], "logged-input\n")

    def test_output_capture_opt_in(self):
        self.start_daemon({"audit_log": "{TMP}/audit.jsonl",
                           "audit_stdout": True, "audit_stderr": True})
        self.run_client("-u", "sh", "-c", "echo out; echo err >&2")
        entries = self.read_audit()
        self.assertEqual(entries[-1]["stdout"], "out\n")
        self.assertEqual(entries[-1]["stderr"], "err\n")


class DenyTest(DaemonCase, unittest.TestCase):
    def test_confirm_timeout_denies(self):
        # auto_accept off + no one answering: the confirm timeout
        # denies the request instead of hanging forever.
        self.start_daemon({"auto_accept": False, "confirm_timeout": 2})
        out = self.run_client("-u", "echo", "never", timeout=20)
        self.assertEqual(out.returncode, 1)
        self.assertIn(b"denied", out.stderr)


class PasswordTest(DaemonCase, unittest.TestCase):
    def test_password_reaches_sudo_unstolen(self):
        """Fake sudo demands a password line on stdin.

        The daemon must suspend its own stdin grabbing while sudo reads,
        so the secret lands in sudo (auth succeeds) and never shows up
        as an "unknown command" in the daemon window.
        """
        rfd, wfd = os.pipe()
        # wfd stays open in the test: the pipe never hits EOF while waiting.
        self.start_daemon(
            {"auto_accept": True},
            stdin=rfd,
            extra_env={"FAKE_SUDO_UNLOCKED": "0",
                       "FAKE_SUDO_PASSWORD": "secret"})
        os.close(rfd)
        result = {}

        def client():
            result["out"] = self.run_client("-u", "echo", "unlocked",
                                            timeout=20)

        t = threading.Thread(target=client)
        t.start()
        time.sleep(2)  # let the worker reach sudo's password read
        os.write(wfd, b"secret\n")
        t.join(timeout=25)
        os.close(wfd)
        out = result["out"]
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, b"unlocked\n")
        self.assertNotIn("unknown command 'secret'", self.daemon_log_text())


if __name__ == "__main__":
    unittest.main()

"""Unit tests for config handling, env filtering, terminal choice."""

import builtins
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import load_script

mod = load_script()


class AsBoolTest(unittest.TestCase):
    def test_values(self):
        ab = mod._as_bool
        self.assertIs(ab(True), True)
        self.assertIs(ab(False), False)
        self.assertIs(ab("true"), True)
        self.assertIs(ab("FALSE"), False)
        self.assertIs(ab("yes"), True)
        self.assertIs(ab("off"), False)
        self.assertIs(ab("0"), False)
        self.assertIs(ab(0), False)
        self.assertIs(ab(2), True)
        self.assertIs(ab(None), False)


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sr-cfg-")
        self.old_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.tmp

    def tearDown(self):
        if self.old_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self.old_xdg
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cfgfile(self):
        return os.path.join(self.tmp, "sudo-request", "config.json")

    def test_fresh_config_has_new_defaults(self):
        cfg, fresh = mod.load_config()
        self.assertTrue(fresh)
        self.assertIs(cfg["keep_sudo"], True)
        self.assertIs(cfg["auto_accept"], False)
        with open(self.cfgfile(), encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertIs(saved["keep_sudo"], True)

    def test_missing_keys_populated_unknowns_kept(self):
        os.makedirs(os.path.dirname(self.cfgfile()), exist_ok=True)
        with open(self.cfgfile(), "w", encoding="utf-8") as fh:
            json.dump({"keep_sudo": False, "custom_note": "keepme"}, fh)
        cfg, fresh = mod.load_config()
        self.assertFalse(fresh)
        self.assertIs(cfg["keep_sudo"], False)
        self.assertEqual(cfg["custom_note"], "keepme")
        self.assertIn("auto_accept", cfg)
        with open(self.cfgfile(), encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertIn("confirm_timeout", saved)
        self.assertEqual(saved["custom_note"], "keepme")

    def test_daemon_validates_bad_values(self):
        d = mod.Daemon({"keep_sudo": "false", "auto_accept": "yes",
                        "keepalive_interval": -5, "confirm_timeout": "0"})
        self.assertIs(d.keep_sudo, False)
        self.assertIs(d.auto_accept, True)
        self.assertEqual(d.keepalive_interval, 60)
        self.assertEqual(d.confirm_timeout, 900.0)

    def test_first_run_defaults_and_first_char(self):
        real_input = builtins.input
        try:
            builtins.input = lambda *a: ""
            d = mod.Daemon(dict(mod.DEFAULT_CONFIG))
            d.first_run_setup()
            self.assertIs(d.keep_sudo, True)
            self.assertIs(d.auto_accept, False)
            # "OK" must not enable keep-sudo via substring match: only
            # the first character counts.
            builtins.input = lambda *a: "k"
            d.first_run_setup()
            self.assertIs(d.keep_sudo, False)
            builtins.input = lambda *a: "OK"
            d.first_run_setup()
            self.assertIs(d.keep_sudo, False)
            builtins.input = lambda *a: "K"
            d.first_run_setup()
            self.assertIs(d.keep_sudo, True)
        finally:
            builtins.input = real_input


class EnvTest(unittest.TestCase):
    def test_hijack_vectors_dropped(self):
        os.environ.update({
            "LD_PRELOAD": "/evil.so",
            "LD_LIBRARY_PATH": "/evil",
            "DYLD_INSERT_LIBRARIES": "x",
            "BASH_ENV": "/evil",
            "ZDOTDIR": "/evil",
            "PYTHONPATH": "/evil",
            "PYTHONSTARTUP": "/evil",
            "NODE_OPTIONS": "--require /e",
            "JAVA_TOOL_OPTIONS": "-agentpath:/e",
            "GCONV_PATH": "/evil",
            "EVIL_FUNC": "() { echo pwned; }",
        })
        try:
            got = dict(mod.env_for_child())
        finally:
            for k in ("LD_PRELOAD", "LD_LIBRARY_PATH",
                      "DYLD_INSERT_LIBRARIES", "BASH_ENV", "ZDOTDIR",
                      "PYTHONPATH", "PYTHONSTARTUP", "NODE_OPTIONS",
                      "JAVA_TOOL_OPTIONS", "GCONV_PATH", "EVIL_FUNC"):
                os.environ.pop(k, None)
        for k in ("LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
                  "BASH_ENV", "ZDOTDIR", "PYTHONPATH", "PYTHONSTARTUP",
                  "NODE_OPTIONS", "JAVA_TOOL_OPTIONS", "GCONV_PATH",
                  "EVIL_FUNC"):
            self.assertNotIn(k, got)

    def test_normal_vars_pass_through(self):
        os.environ["SR_TEST_KEEPME_XYZ"] = "yes"
        try:
            got = dict(mod.env_for_child())
        finally:
            del os.environ["SR_TEST_KEEPME_XYZ"]
        self.assertEqual(got["SR_TEST_KEEPME_XYZ"], "yes")
        self.assertIn("PATH", got)
        self.assertIn("HOME", got)


class TerminalTest(unittest.TestCase):
    def test_priority(self):
        real_which = mod.shutil.which
        mod.shutil.which = lambda t: t in ("termA", "termB")
        old_term = os.environ.get("TERMINAL")
        try:
            os.environ["TERMINAL"] = "termB"
            # Explicit config beats $TERMINAL.
            self.assertEqual(mod.find_terminal("termA"), "termA")
            # $TERMINAL beats autodetect; missing config falls back.
            self.assertEqual(mod.find_terminal(None), "termB")
            self.assertEqual(mod.find_terminal("missing"), "termB")
            del os.environ["TERMINAL"]
            self.assertEqual(mod.find_terminal("termB"), "termB")
        finally:
            mod.shutil.which = real_which
            if old_term is None:
                os.environ.pop("TERMINAL", None)
            else:
                os.environ["TERMINAL"] = old_term

    def test_command_shapes(self):
        self.assertEqual(mod.terminal_command("gnome-terminal", ["a"]),
                         ["gnome-terminal", "--", "a"])
        self.assertEqual(mod.terminal_command("wezterm", ["a"]),
                         ["wezterm", "start", "--", "a"])
        self.assertEqual(mod.terminal_command("kitty", ["a"]), ["kitty", "a"])
        self.assertEqual(mod.terminal_command("konsole", ["a"]),
                         ["konsole", "-e", "a"])


if __name__ == "__main__":
    unittest.main()

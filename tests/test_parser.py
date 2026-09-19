"""Unit tests for the hand-rolled CLI parser.

Only argv[0] is ever read as an option, and only when it starts with '-'.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import load_script

mod = load_script()


class ParseTest(unittest.TestCase):
    def test_plain_command(self):
        self.assertEqual(mod.parse_cli(["printf", "hi"]),
                         ("run", False, ["printf", "hi"]))

    def test_passthrough(self):
        self.assertEqual(mod.parse_cli(["-p", "printf", "hi"]),
                         ("run", False, ["printf", "hi"]))
        self.assertEqual(mod.parse_cli(["-p", "-weird", "--foo"]),
                         ("run", False, ["-weird", "--foo"]))

    def test_delegated(self):
        self.assertEqual(mod.parse_cli(["-u", "echo", "x"]),
                         ("run", True, ["echo", "x"]))
        self.assertEqual(mod.parse_cli(["-up", "echo", "x"]),
                         ("run", True, ["echo", "x"]))
        self.assertEqual(mod.parse_cli(["-pu", "echo", "x"]),
                         ("run", True, ["echo", "x"]))

    def test_lone_dash_is_command(self):
        self.assertEqual(mod.parse_cli(["-"]), ("run", False, ["-"]))

    def test_help_and_version(self):
        for argv in (["-h"], ["--help"]):
            with self.assertRaises(SystemExit) as ctx:
                mod.parse_cli(argv)
            self.assertEqual(ctx.exception.code, 0)
        for argv in (["-v"], ["-uh"], ["-uv"]):
            with self.assertRaises(SystemExit) as ctx:
                mod.parse_cli(argv)
            self.assertEqual(ctx.exception.code, 0)

    def test_unknown_options_rejected(self):
        for argv in (["-x"], ["-V"], ["-flag-locking-command"],
                     ["--"], ["--version"], ["--foo"]):
            with self.assertRaises(SystemExit) as ctx:
                mod.parse_cli(argv)
            self.assertEqual(ctx.exception.code, 1, argv)

    def test_missing_command_rejected(self):
        for argv in ([], ["-u"], ["-p"]):
            with self.assertRaises(SystemExit) as ctx:
                mod.parse_cli(argv)
            self.assertEqual(ctx.exception.code, 1, argv)

    def test_daemon_token(self):
        action, delegated, command = mod.parse_cli([mod._DAEMON_TOKEN])
        self.assertEqual((action, delegated, command), ("daemon", False, []))
        # The token must stand alone.
        with self.assertRaises(SystemExit) as ctx:
            mod.parse_cli([mod._DAEMON_TOKEN, "extra"])
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()

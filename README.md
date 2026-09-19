# sudo-request

A `sudo` alternative with a human in the loop. Instead of typing your
password into whatever terminal happens to ask, every privileged command
is routed through a **daemon running in its own terminal window**, where
you see each request and approve or deny it. Single file, standard
library only (`sudo-request`, Python 3).

> AI was used heavily during development, with human review and testing
> of all code. This is a personal tool I wanted and I'm sharing it in
> case it's useful to others.

Ideal to use with an app like OpenCode where commands get run for you:
the agent runs `sudo-request …` instead of `sudo …`, and **you** approve
each privileged command in the daemon window. See `SKILL.md` — drop it
into your agent's skills so it knows how `sudo-request` behaves.

```sh
sudo-request pacman -Syu
echo foo | sudo-request tee /etc/example.conf
sudo-request -u paru -Syu
```

## How it works (read this first)

The important part is **who is in control**:

- The **daemon runs as you, in your terminal, and answers only to you.**
  It holds the sudo timestamp, shows every request, asks for approval,
  and executes. It is started **automatically** the first time you run
  `sudo-request` (a terminal window pops up) and keeps serving until you
  close it.
- The **`sudo-request` command is only a messenger.** It delivers your
  command (plus cwd/environment) to the daemon over a Unix socket and
  streams stdin/stdout/stderr back. It cannot approve anything, change
  settings, or control the daemon in any way. Approval happens
  exclusively by pressing keys in the daemon window.
- The daemon's control entrypoint is internal and undocumented on
  purpose — there is no supported way to drive the daemon except
  sitting in front of its terminal.

```
 your shell                  daemon terminal (yours, auto-spawned)
 ──────────                  ─────────────────────────────────────
 sudo-request cmd ──socket─► [sudo] authenticating (if needed)
                             [0001] REQUEST 'pacman' '-Syu'
                             [0001] Allow? [y/N] ──► you press y/n
                             [0001] ACCEPTED, runs via sudo, streams back
```

Because sudo timestamps are per-terminal (`tty_tickets`), the daemon's
terminal is the *only* place that ever holds one. Your everyday shells
stay unauthenticated.

## Usage

Only the first argument is ever read as an option, and only when it
starts with `-`. Everything else is the command, verbatim.

| Option | Meaning                                                        |
| ------ | -------------------------------------------------------------- |
| `-u`   | delegated mode: run as your user with a valid sudo timestamp, so the command itself may call `sudo` |
| `-p`   | pass everything after this point through verbatim (for commands starting with `-`) |
| `-h`   | show help (`--help` also works, nothing else long does)        |
| `-v`   | print version                                                  |

Letters combine: `sudo-request -up command …`. A leading `-p` forces
literal treatment: `sudo-request -p -weird-flag` runs `-weird-flag`
instead of erroring on it.

## Daemon window keys (no Enter needed)

| Key | Effect                                                        |
| --- | ------------------------------------------------------------- |
| `y` | approve the pending request (`n`/Enter denies)                |
| `a` | toggle auto-accept on/off                                     |
| `k` | toggle keep-sudo (stay authenticated) on/off                  |
| `s` | show current settings                                         |
| `h` | show the reminder                                             |

The same keys work while an `Allow?` prompt is shown: they toggle/show
and ask again instead of answering, so a keystroke can never leak into
an answer. While `sudo` reads a password, key grabbing pauses so your
password reaches sudo untouched.

## Config (`~/.config/sudo-request/config.json`)

Created with defaults on first run; missing keys are filled in
automatically. Shown in the daemon window on startup.

| Key                | Default | Meaning                                              |
| ------------------ | ------- | ---------------------------------------------------- |
| `keep_sudo`        | `true`  | keep the sudo timestamp alive                        |
| `auto_accept`      | `false` | skip confirmation prompts                            |
| `keepalive_interval` | `60`  | seconds between timestamp refreshes                  |
| `confirm_timeout`  | `900`   | seconds before an unanswered prompt denies           |
| `terminal`         | `null`  | preferred terminal emulator (else `$TERMINAL`, else autodetect) |
| `audit_log`        | `null`  | path of the JSON-lines audit log (`null` = off)      |
| `audit_command`    | `true`  | log the command                                      |
| `audit_env`        | `true`  | log the environment                                  |
| `audit_stdin`      | `true`  | log piped stdin (capped at 64 KiB)                   |
| `audit_exit`       | `true`  | log the exit code                                    |
| `audit_stdout`     | `false` | log stdout (capped at 1 MiB; off so the log can't fill up fast) |
| `audit_stderr`     | `false` | log stderr (same cap)                                |

Denied and failed-authentication requests are logged too (without an
exit code).

Toggles pressed in the daemon window (`a`/`k`) apply to the running
daemon only and are deliberately never written back: restarting
restores the config values. To change them permanently, edit the JSON
— or delete it, and the daemon asks again on next start (first-run
setup).

Environment: everything is passed through **except** known hijack
vectors (`LD_*`/`DYLD_*`, shell-init vars, locale-path vars,
interpreter library vars, shellshock-style function exports) — a
compromised caller can't smuggle those past your approval. `sudo`
applies its own filtering on top.

## Install

Releases (Codeberg upstream, GitHub mirror):

- <https://codeberg.org/marvin1099/sudo-request/releases>
- <https://github.com/marvin1099/sudo-request/releases>

Quickstart — pull the file straight into `~/.local/bin`:

```sh
mkdir -p ~/.local/bin
curl -fSL -o ~/.local/bin/sudo-request \
  https://codeberg.org/marvin1099/sudo-request/releases/download/v0.3.0/sudo-request
chmod +x ~/.local/bin/sudo-request
```

Or from source: copy the `sudo-request` file anywhere on your `PATH`
and make it executable.

## Skill install (for AI agents)

`SKILL.md` teaches an agent to use `sudo-request` instead of `sudo`.
Agents all use different skill folders, so place the file yourself —
OpenCode shown as example (replace the folder with your setup's):

```sh
curl -fSL -o ~/Downloads/SKILL.sudo-request.md \
  https://codeberg.org/marvin1099/sudo-request/releases/download/v0.3.0/SKILL.md
mkdir -p ~/.config/opencode/skills/sudo-request
cp ~/Downloads/SKILL.sudo-request.md \
  ~/.config/opencode/skills/sudo-request/SKILL.md
```

## Testing

Standard library `unittest` only — no dependencies:

```sh
cd sudo-request
python3 -m unittest discover -s tests -v
```

The suite never touches your real daemon, config, or sudo. It uses:

- **`tests/fixtures/fake-sudo`** — a `sudo` double put first on `PATH`.
  `FAKE_SUDO_UNLOCKED=1` pretends the timestamp is valid;
  `FAKE_SUDO_UNLOCKED=0` makes `sudo -v` read one "password" line from
  stdin (checked against `FAKE_SUDO_PASSWORD`), which is how the suite
  proves the daemon never steals sudo's password keystrokes.
- **Fake terminals** — `test_console_pty.py` drives the daemon console
  through a real `pty` pair: the master end plays the user, so instant
  single-keypress handling (toggles, answers, escape-swallowing,
  stale-answer draining) is tested exactly like in a terminal window,
  without opening one.

| File                    | What it covers                                              |
| ----------------------- | ----------------------------------------------------------- |
| `test_parser.py`        | CLI matrix: flags, `-p` passthrough, combos, rejections     |
| `test_config_env.py`    | config defaults/populate, bool coercion, env blacklist, terminal priority, first-run setup |
| `test_console_pty.py`   | instant keys, answers, Enter-deny, ESC swallowing, draining |
| `test_integration.py`   | live daemon+client: stdio, exit codes, stdin, cwd isolation, audit log, timeout-deny, sudo-password path |

Long-running or timing-sensitive paths use generous timeouts and every
test tears its daemon down, so a failure reports instead of hanging.

# sudo-request

A `sudo` alternative with a human in the loop: every privileged command
goes through a **daemon in its own terminal window**, where you approve
or deny it. Single file, standard library only (Python 3).

> AI was used heavily during development, with human review and testing
> of all code. Personal tool, shared in case it's useful to others.

Ideal with an app like OpenCode where commands get run for you: the
agent runs `sudo-request …` instead of `sudo …`, and **you** approve
each privileged command in the daemon window. See `SKILL.md`.

```sh
sudo-request pacman -Syu
echo foo | sudo-request tee /etc/example.conf
sudo-request -u paru -Syu
```

- [Download & Install](#download--install)
- [Skill install (for AI agents)](#skill-install-for-ai-agents)
- [How it works](#how-it-works-read-this-first)
- [Usage](#usage)
- [Daemon window keys](#daemon-window-keys-no-enter-needed)
- [Config](#config)
- [Testing](#testing)

Requirements: Linux, Python 3, `sudo`, and a terminal emulator.

## Download & Install

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
Skill folders differ per agent, so place it yourself — OpenCode shown
as example (replace the folder with your setup's):

```sh
curl -fSL -o ~/Downloads/SKILL.sudo-request.md \
  https://codeberg.org/marvin1099/sudo-request/releases/download/v0.3.0/SKILL.md
mkdir -p ~/.config/opencode/skills/sudo-request
cp ~/Downloads/SKILL.sudo-request.md \
  ~/.config/opencode/skills/sudo-request/SKILL.md
```

## How it works (read this first)

**Who is in control:**

- The **daemon runs as you, in your terminal, and answers only to you.**
  It holds the sudo timestamp and executes. It starts **automatically**
  on first use (a terminal window pops up) and serves until you close it.
- The **`sudo-request` command is only a messenger** over a Unix socket.
  It cannot approve anything — approval happens exclusively by pressing
  keys in the daemon window.
- The daemon's control entrypoint is internal and undocumented on
  purpose.

```
 your shell                  daemon terminal (yours, auto-spawned)
 ──────────                  ─────────────────────────────────────
 sudo-request cmd ──socket─► [sudo] authenticating (if needed)
                             [0001] REQUEST 'pacman' '-Syu'
                             [0001] Allow? [y/N] ──► you press y/n
                             [0001] ACCEPTED, runs via sudo, streams back
```

Sudo timestamps are per-terminal (`tty_tickets`), so the daemon's
terminal is the *only* place that ever holds one — your other shells
stay unauthenticated.

## Usage

Only the first argument is ever read as an option, and only when it
starts with `-`. Everything else is the command, verbatim.

| Option | Meaning                                                        |
| ------ | -------------------------------------------------------------- |
| `-u`   | delegated mode: run as your user with a usable sudo timestamp  |
| `-p`   | pass the rest through verbatim (for commands starting with `-`) |
| `-h`   | show help (`--help` also works, nothing else long does)        |
| `-v`   | print version                                                  |

Letters combine (`-up`). A leading `-p` forces literal treatment:
`sudo-request -p -weird-flag` runs `-weird-flag` instead of erroring.

## Daemon window keys (no Enter needed)

| Key | Effect                                                        |
| --- | ------------------------------------------------------------- |
| `y` | approve (`n`/Enter denies)                                    |
| `a` | toggle auto-accept on/off                                     |
| `k` | toggle keep-sudo (stay authenticated) on/off                  |
| `s` | show current settings                                         |
| `h` | show the reminder                                             |

The same keys work during an `Allow?` prompt (toggle/show, then ask
again). While `sudo` reads a password, key grabbing pauses.

## Config

Lives at `~/.config/sudo-request/config.json` — created with defaults,
missing keys filled in automatically, path shown in the daemon window.

| Key                | Default | Meaning                                              |
| ------------------ | ------- | ---------------------------------------------------- |
| `keep_sudo`        | `true`  | keep the sudo timestamp alive                        |
| `auto_accept`      | `false` | skip confirmation prompts                            |
| `keepalive_interval` | `60`  | seconds between timestamp refreshes                  |
| `confirm_timeout`  | `900`   | seconds before an unanswered prompt denies           |
| `terminal`         | `null`  | preferred terminal (`$TERMINAL`, else autodetect)     |
| `audit_log`        | `null`  | JSON-lines audit log path (`null` = off)             |
| `audit_command/env/stdin/exit` | `true` | what gets logged (stdin capped at 64 KiB)   |
| `audit_stdout/stderr` | `false` | log output (1 MiB cap; off to keep the log small) |

Denied and failed-auth requests are logged too (no exit code).
Toggles (`a`/`k`) are never written back — restart restores config
values; edit the JSON (or delete it for a fresh first-run setup) to
change them permanently.

Environment passes through **except** known hijack vectors (`LD_*` /
`DYLD_*`, shell-init, locale-path and interpreter-library vars,
shellshock-style exports); `sudo` filters on top of that.

## Testing

Standard library `unittest` only:

```sh
cd sudo-request
python3 -m unittest discover -s tests -v
```

Never touches your real daemon, config, or sudo. Uses
**`tests/fixtures/fake-sudo`** (a `sudo` double, incl. a password mode
proving the daemon never steals sudo's keystrokes) and **fake
terminals** (`test_console_pty.py` drives the console through a `pty`
pair). Timeouts plus per-test teardown mean failures report instead of
hanging.

| File                    | What it covers                                              |
| ----------------------- | ----------------------------------------------------------- |
| `test_parser.py`        | flags, `-p` passthrough, combos, rejections                 |
| `test_config_env.py`    | config defaults/populate, env blacklist, terminal, first-run |
| `test_console_pty.py`   | instant keys, answers, ESC swallowing, draining             |
| `test_integration.py`   | live daemon+client: stdio, exit codes, audit log, deny paths |

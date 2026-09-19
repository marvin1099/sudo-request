---
name: sudo-request
description: Run privileged commands via sudo-request instead of sudo. The human approves each command in a separate terminal window.
---

# sudo-request

Use `sudo-request` (not `sudo`) for privileged commands where it is
installed. Same syntax, but the **human approves each command** in a
separate auto-spawned terminal window.

```sh
sudo-request COMMAND [ARGS...]
sudo-request -u COMMAND [ARGS...]   # run as user, sudo is unlocked inside ("paru" needs this as example)
sudo-request -p -weird-flag         # -p: pass dash-leading commands verbatim
```

Rules: only the **first** argument is an option and only if it starts
with `-` (short flags, combinable: `-u -p -h -v`). Everything else is
the command verbatim — `sudo-request cmd -u` passes `-u` to `cmd`.
Stdin piping works.

Behavior: commands may **wait on human approval** — be patient, never
retry-loop, never try to answer or automate the prompt. Denial exits
non-zero with `request denied by user`: report it and stop. Exit
codes and stdio pass through transparently.

Never drive, configure, or kill the daemon, and no password-pipe tricks
around it. On `no terminal emulator found`, tell the human.

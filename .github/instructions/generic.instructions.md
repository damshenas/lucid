---
applyTo: '**'
---

1- never run any code on local host. Everything must be tested with docker containers. docker build will do the tests.

2- to test on the real remote host (hostname `bigli`), connect via `ssh nuc@192.168.178.222` (user must type the password themselves, never send it through a tool). The stack runs there under `podman compose` from `~/lucid` and is often already up — never restart, rebuild, or stop containers there without asking first. Use read-only checks only (e.g. `podman ps -a --filter name=lucid`, `podman logs lucid`) unless explicitly told to change something. Must use interactive session.

3- minimal code. minimal description. only necessary. avoid making bloated codes and documentations. focus on clarity and simplicity.
# Security

## Reporting a problem

Please **don't open a public issue** for security problems. Report them
privately through GitHub instead: on the repository page, go to
**Security → Report a vulnerability**.

Include what you found, how to reproduce it, and what an attacker could do with
it. You'll get an answer as soon as possible; RPC Buddy is maintained in spare
time, so please allow a few days.

## Scope

RPC Buddy runs as a Flatpak with narrow permissions, opens no network ports
and executes nothing it downloads. Data from outside that it handles: Discord's
public game list, cover images, and the music metadata (titles, artists,
covers) that players and websites publish on the desktop session bus.

The threat model and the findings of the last review are in
[DESIGN.md §13](DESIGN.md#13-security-assessment-2026-11).

## Supported versions

Only the latest release gets fixes.

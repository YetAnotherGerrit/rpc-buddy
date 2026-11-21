# Future ideas

Ideas that are explicitly **not** part of the first iteration, and might never be.

## Generic fallback for games unknown to Discord

Steam games without an entry in Discord's detectable applications list
(`/applications/detectable`, matched via `third_party_skus` with
`distributor: steam`) currently show no presence at all.

Idea: register a generic "rpc-buddy" application in the Discord Developer
Portal and use it as a fallback:

- Shows as "Playing rpc-buddy"
- `details`: the game name (from the Steam store API)
- `large_image`: the Steam cover art (external https URL)
- Elapsed time since the game started

## Cover art for music

MPRIS players often only provide a local `file://` cover (e.g. a browser
playing Deezer web points to a cached image inside its own data folder),
which Discord cannot display. Discord does accept external https images (it
proxies them via `mp:external/…`).

**Decided (2026-11): no online cover lookups.** Looking covers up by
artist/title (Deezer search API, MusicBrainz + Cover Art Archive, iTunes)
would send what the user listens to to a third party — not worth it.
Without a cover, Discord shows the RPC Buddy app icon.

Ideas that need no lookup, in case covers come up again:

- **YouTube / YouTube Music in a browser**: the page URL contains the video
  id (`watch?v=<id>`), so `https://i.ytimg.com/vi/<id>/hqdefault.jpg` is the
  cover (4:3 with bars for album art). Verified 2026-11. Other web players
  (Deezer, TIDAL, Spotify, Apple Music) report the current page, not the
  track, so this doesn't work for them.
- **Plasma Browser Integration** (KDE): its extension republishes a page's
  Media Session — probably including the original https cover — as the MPRIS
  player `plasma-browser-integration`. Not verified; may not work with a
  Flatpak browser.

## `registry.vdf` as an additional Steam detector

Older Steam clients reportedly wrote `RunningAppID` into `~/.steam/registry.vdf`
while a game was running. The current 64-bit Linux client (`steamrt64`) does
not, not even during a game (verified 2026-11-19). Only worth adding if log
detection turns out to fail for some users and they run a client that still
writes the key. The Steam module supports several detectors, so this would be
one more.

## More game sources besides Steam

Heroic, Lutris, emulators, etc. The module interface should be designed so
these can be added later without changes to the core.

## Third-party modules

Letting users write and install their own modules (e.g. a drop-in plugin
directory or an out-of-process D-Bus/stdin interface). Dropped from the
initial requirements: modules are maintainer-only for now, but the internal
structure stays modular.

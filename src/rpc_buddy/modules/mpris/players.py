"""Which MPRIS players count as music sources, and what to call them.

MPRIS bus names look like ``org.mpris.MediaPlayer2.<player>[.instance<n>]``.
"""

from dataclasses import dataclass
from urllib.parse import urlparse

BUS_PREFIX = "org.mpris.MediaPlayer2."

# Dedicated music players: player key -> name shown in Discord.
MUSIC_PLAYERS = {
    "amberol": "Amberol",
    "audacious": "Audacious",
    "cantata": "Cantata",
    "cider": "Cider",
    "clementine": "Clementine",
    "deezer": "Deezer",
    "elisa": "Elisa",
    "feishin": "Feishin",
    "g4music": "Gapless",
    "gapless": "Gapless",
    "lollypop": "Lollypop",
    "mpd": "MPD",
    "quodlibet": "Quod Libet",
    "rhythmbox": "Rhythmbox",
    "strawberry": "Strawberry",
    "supersonic": "Supersonic",
    "tauon": "Tauon",
    "tidal-hifi": "TIDAL",
    "youtube-music": "YouTube Music",
}

# Apps that register under a generic (e.g. Electron/Chromium) bus name but
# report a recognisable MPRIS Identity: lowercased identity -> shown name.
MUSIC_IDENTITIES = {
    "deezer": "Deezer",
    "tidal": "TIDAL",
    "tidal hifi": "TIDAL",
    "youtube music": "YouTube Music",
}

# Browsers: only accepted when the track URL belongs to a music service.
BROWSERS = (
    "brave",
    "chrome",
    "chromium",
    "edge",
    "epiphany",
    "firefox",
    "floorp",
    "librewolf",
    "opera",
    "plasma-browser-integration",
    "vivaldi",
    "zen",
)

# Music web services: host (or parent domain) -> shown name.
MUSIC_SITES = {
    "deezer.com": "Deezer",
    "tidal.com": "TIDAL",
    "music.youtube.com": "YouTube Music",
    "soundcloud.com": "SoundCloud",
    "music.apple.com": "Apple Music",
    "bandcamp.com": "Bandcamp",
}

# Discord shows Spotify by itself (account connection), so never duplicate it.
IGNORED_PLAYERS = ("spotify", "spotifyd", "ncspot")
IGNORED_SITES = ("open.spotify.com",)


def player_key(bus_name: str) -> str:
    """``org.mpris.MediaPlayer2.firefox.instance_1_23`` -> ``firefox``."""
    return bus_name.removeprefix(BUS_PREFIX).split(".", 1)[0].lower()


def _site(url: str | None, sites) -> str | None:
    """Return the matching key of ``sites`` for ``url``'s host, if any."""
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    for site in sites:
        if host == site or host.endswith("." + site):
            return site
    return None


def source_name(bus_name: str, identity: str | None, url: str | None) -> str | None:
    """Name of the music source to show, or None if this player is not music."""
    key = player_key(bus_name)
    if key in IGNORED_PLAYERS or _site(url, IGNORED_SITES):
        return None
    if key in MUSIC_PLAYERS:
        return MUSIC_PLAYERS[key]
    if identity and identity.strip().lower() in MUSIC_IDENTITIES:
        return MUSIC_IDENTITIES[identity.strip().lower()]
    if key in BROWSERS:
        site = _site(url, MUSIC_SITES)
        return MUSIC_SITES[site] if site else None
    return None


@dataclass(frozen=True)
class Track:
    title: str
    artists: tuple[str, ...] = ()
    album: str | None = None
    art_url: str | None = None
    length: float | None = None  # seconds
    url: str | None = None

    @property
    def artist(self) -> str | None:
        return ", ".join(self.artists) or None


def track_from_metadata(meta: dict) -> Track | None:
    """Build a Track from an (unwrapped) MPRIS Metadata dict."""
    title = (meta.get("xesam:title") or "").strip()
    if not title:
        return None
    artists = meta.get("xesam:artist") or ()
    if isinstance(artists, str):
        artists = (artists,)
    length = meta.get("mpris:length")
    return Track(
        title=title,
        artists=tuple(a.strip() for a in artists if a and a.strip()),
        album=(meta.get("xesam:album") or "").strip() or None,
        art_url=meta.get("mpris:artUrl") or None,
        length=length / 1_000_000 if isinstance(length, int) and length > 0 else None,
        url=meta.get("xesam:url") or None,
    )

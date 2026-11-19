"""Registry of all modules. Add new module classes here."""

from rpc_buddy.module import Module
from rpc_buddy.modules.mpris import MprisModule
from rpc_buddy.modules.steam import SteamModule

MODULES: list[type[Module]] = [
    SteamModule,
    MprisModule,
]

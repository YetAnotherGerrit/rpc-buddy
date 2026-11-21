"""Loads cover images (e.g. a game's cover from Discord's CDN) for the GUI."""

import logging
from collections import OrderedDict
from collections.abc import Callable

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from rpc_buddy.detectable import USER_AGENT

log = logging.getLogger(__name__)

MAX_CACHED = 50


class CoverLoader(QObject):
    """Downloads https images once and keeps the last few in memory."""

    def __init__(self) -> None:
        super().__init__()
        self._network = QNetworkAccessManager(self)
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._waiting: dict[str, list[Callable[[QPixmap], None]]] = {}

    def request(self, url: str | None, callback: Callable[[QPixmap], None]) -> None:
        """Call ``callback`` with the image, now (cached) or once downloaded."""
        if not url or not url.startswith("https://"):
            return
        if url in self._cache:
            self._cache.move_to_end(url)
            callback(self._cache[url])
            return
        if url in self._waiting:
            self._waiting[url].append(callback)
            return
        self._waiting[url] = [callback]
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, USER_AGENT)
        reply = self._network.get(request)
        reply.finished.connect(lambda: self._finished(url, reply))

    def _finished(self, url: str, reply: QNetworkReply) -> None:
        callbacks = self._waiting.pop(url, [])
        pixmap = QPixmap()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pixmap.loadFromData(bytes(reply.readAll()))
        else:
            log.debug("Could not load cover %s: %s", url, reply.errorString())
        reply.deleteLater()
        if pixmap.isNull():
            return
        self._cache[url] = pixmap
        while len(self._cache) > MAX_CACHED:
            self._cache.popitem(last=False)
        for callback in callbacks:
            callback(pixmap)

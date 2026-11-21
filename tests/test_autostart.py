from rpc_buddy import APP_ID
from rpc_buddy.autostart import write_desktop_entry
from rpc_buddy.portal import request_path, uri_to_path


def test_request_path_escapes_sender():
    assert request_path(":1.234", "tok") == "/org/freedesktop/portal/desktop/request/1_234/tok"


def test_desktop_entry_written_and_removed(tmp_path):
    write_desktop_entry(True, tmp_path)
    entry = tmp_path / f"{APP_ID}.desktop"
    text = entry.read_text()
    assert "--background" in text
    assert "[Desktop Entry]" in text
    write_desktop_entry(False, tmp_path)
    assert not entry.exists()


def test_uri_to_path_decodes_portal_uris():
    uri = "file:///run/user/1000/doc/AbC123/My%20Steam"
    assert uri_to_path(uri) == "/run/user/1000/doc/AbC123/My Steam"

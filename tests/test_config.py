from rpc_buddy.config import Config


def test_defaults_when_missing(tmp_path):
    config = Config.load(tmp_path / "missing.toml")
    assert config.paused is False
    assert config.module_enabled("steam") is True


def test_roundtrip(tmp_path):
    path = tmp_path / "sub" / "config.toml"
    config = Config.load(path)
    config.paused = True
    config.set_module_enabled("steam", False)
    config.save()
    loaded = Config.load(path)
    assert loaded.paused is True
    assert loaded.module_enabled("steam") is False


def test_broken_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("this is [not toml")
    assert Config.load(path).paused is False

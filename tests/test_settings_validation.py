import pytest

import jugnu_core


@pytest.fixture
def load_settings(tmp_path):
    return lambda: jugnu_core.load_dark_mode(tmp_path / "jugnu_settings.json")


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        "null",
        '"hello"',
        "123",
    ],
)
def test_load_settings_returns_default_for_non_dict_json(load_settings, tmp_path, content):
    settings_file = tmp_path / "jugnu_settings.json"
    settings_file.write_text(content, encoding="utf-8")

    assert load_settings() is True


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"dark_mode": true}', True),
        ('{"dark_mode": false}', False),
        ('{}', True),
    ],
)
def test_load_settings_handles_valid_dict(load_settings, tmp_path, content, expected):
    settings_file = tmp_path / "jugnu_settings.json"
    settings_file.write_text(content, encoding="utf-8")

    assert load_settings() is expected


def test_load_settings_handles_invalid_json(load_settings, tmp_path):
    settings_file = tmp_path / "jugnu_settings.json"
    settings_file.write_text("{invalid json", encoding="utf-8")

    assert load_settings() is True


def test_load_settings_handles_missing_file(load_settings):
    assert load_settings() is True

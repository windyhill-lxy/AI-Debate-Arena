from app.services.runtime_settings import RuntimeSettings, apply_runtime_settings, load_runtime_settings


def test_runtime_settings_prefill_and_save(tmp_path, monkeypatch) -> None:
    path = tmp_path / "runtime_settings.json"
    monkeypatch.setattr("app.services.runtime_settings.RUNTIME_SETTINGS_PATH", path)

    original = RuntimeSettings(
        api_keys={"deepseek": "sk-old"},
        models={"aff_1": "deepseek-v4-pro"},
        defaults={"deepseek_base_url": "https://example.test/v1"},
    )
    apply_runtime_settings(original)

    loaded = load_runtime_settings()
    assert loaded.api_keys["deepseek"] == "sk-old"
    assert loaded.models["aff_1"] == "deepseek-v4-pro"
    assert loaded.defaults["deepseek_base_url"] == "https://example.test/v1"

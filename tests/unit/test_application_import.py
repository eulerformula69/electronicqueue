def test_application_imports_without_legacy_queue_mode_services():
    from app.application import app

    assert app is not None

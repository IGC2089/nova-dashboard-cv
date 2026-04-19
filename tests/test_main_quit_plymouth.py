import subprocess


def test_quit_plymouth_is_importable():
    """_quit_plymouth must exist as a module-level function in main."""
    import main
    assert hasattr(main, '_quit_plymouth'), \
        "_quit_plymouth not found in main.py"
    assert callable(main._quit_plymouth)


def test_quit_plymouth_safe_when_not_installed(monkeypatch):
    """_quit_plymouth must not raise when the plymouth binary is missing."""
    import main

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("plymouth not found")

    monkeypatch.setattr('subprocess.run', fake_run)
    main._quit_plymouth()  # must not raise


def test_quit_plymouth_safe_on_timeout(monkeypatch):
    """_quit_plymouth must not raise on subprocess timeout."""
    import main

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=['plymouth'], timeout=2.0)

    monkeypatch.setattr('subprocess.run', fake_run)
    main._quit_plymouth()  # must not raise

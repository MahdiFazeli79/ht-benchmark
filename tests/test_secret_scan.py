"""Fail-closed secret scanner tests (generation-unit pre-flight)."""
from htbench import secret_scan as S


def test_clean_text_passes():
    text = "x_code = 11\nhandle = 'top.a'\nrecall = 1.0\n"
    assert S.scan_text(text, "f") == []


def test_known_key_prefixes_caught():
    # Synthetic, non-real tokens shaped like real keys.
    samples = [
        "key = 'sk-ant-" + "A1b2C3d4E5f6G7h8I9j0" + "'",
        "TOKEN=ghp_" + "0123456789abcdef0123456789abcdef0123",
        "aws = 'AKIA" + "ABCDEFGHIJKLMNOP" + "'",
    ]
    for s in samples:
        assert S.scan_text(s, "f"), f"missed: {s}"


def test_high_entropy_assignment_caught():
    hit = S.scan_text("api_key = 'Zx9Qk2Lm7Pv3Rt8Wn4Hb6Yc1Fd5Gj0'", "f")  # pragma: allowlist secret
    assert hit


def test_env_var_reference_not_flagged():
    # A reference to a secret via env/template is not a leaked secret.
    assert S.scan_text("api_key = '${OPENAI_API_KEY}'", "f") == []
    assert S.scan_text('token = "{{ secrets.GH_TOKEN }}"', "f") == []


def test_main_exit_codes(tmp_path):
    clean = tmp_path / "ok.py"
    clean.write_text("x = 1\n")
    assert S.main([str(clean)]) == 0

    bad = tmp_path / "leak.py"
    bad.write_text("key = 'sk-ant-A1b2C3d4E5f6G7h8I9j0K'\n")  # pragma: allowlist secret
    assert S.main([str(bad)]) == 1

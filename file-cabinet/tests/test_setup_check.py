import sys

from filecabinet import fetch


def test_check_on_a_fresh_windows_computer(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(fetch.platform, "system", lambda: "Windows")
    monkeypatch.setitem(sys.modules, "llama_cpp", None)  # not installed
    assert fetch.check(tmp_path) == 1
    out = capsys.readouterr().out
    assert "MISSING llama-cpp-python" in out
    assert "Build Tools for Visual Studio" in out and "CMAKE_ARGS" in out
    assert "no chat model" in out


def test_check_when_ready(monkeypatch, tmp_path, capsys):
    class FakeLlama:
        __version__ = "0.3.38"

        @staticmethod
        def llama_supports_gpu_offload():
            return True

    monkeypatch.setitem(sys.modules, "llama_cpp", FakeLlama)
    (tmp_path / "qwen2.5-3b-instruct-q4_k_m.gguf").write_bytes(b"x")
    (tmp_path / "qwen2.5-3b-instruct-q4_k_m.gguf.calibration.json").write_text('{"threshold": 0.8}')
    (tmp_path / "bge-small-en-v1.5-f16.gguf").write_bytes(b"x")
    assert fetch.check(tmp_path) == 0
    out = capsys.readouterr().out
    assert "can use the GPU" in out and "confidence cutoff 0.8" in out and "Ready." in out

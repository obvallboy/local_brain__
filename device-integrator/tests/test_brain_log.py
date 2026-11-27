"""The integration brain's alerts reach the Brain's memory, and it can answer about them."""

from integration.brain_log import log_alerts_to_brain
from integration.engine import run_sim
from integrator.assistant import import_filecabinet


def test_alerts_become_memories(tmp_path):
    brain, _ = run_sim(ticks=30, fuzz_after=8, anomaly=True)
    assert brain.alerts
    db = str(tmp_path / "cabinet.db")
    assert log_alerts_to_brain(brain.alerts, db) == len(brain.alerts)

    fc = import_filecabinet()
    cab = fc.FileCabinet(store=fc.Store(db))
    answer = cab.ask("what went wrong with the sensor today?")
    assert answer.label.value == "I remember"
    assert "temp-01" in answer.text and "corrupt" in answer.text


def test_engine_cli_logs_to_brain(tmp_path, capsys):
    from integration.engine import main
    db = str(tmp_path / "cabinet.db")
    main(["--sim", "--ticks", "12", "--fuzz-after", "4", "--log-to-brain", db])
    assert "Logged 1 alert(s) to the Brain's memory" in capsys.readouterr().out

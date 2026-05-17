"""
Test del worker (PR #2). Non tocca rete/DB reali: tutto via MagicMock.
Coperture:
  - claim ritorna None quando la coda e' vuota o quando l'RPC fallisce
  - claim ritorna il primo job quando l'RPC restituisce dati
  - _process_job chiama _process_message_impl con i kwargs giusti dal payload
  - _mark_done passa status='done'
  - _mark_failed_or_dead reschedula in 'pending' con backoff esponenziale
    sotto max_attempts, marca 'dead' al raggiungimento di max_attempts
  - main_loop processa un job e si ferma quando _should_stop e' True
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
import main  # noqa: E402
import worker  # noqa: E402


def _build_job(**overrides) -> dict:
    base = {
        "id": "11111111-1111-4111-8111-111111111111",
        "kind": "process_message",
        "status": "processing",
        "attempts": 1,
        "max_attempts": 3,
        "message_sid": "SM_TEST_001",
        "payload": {
            "from_number": "+393331234567",
            "body": "Ho mal di testa",
            "num_media": 0,
            "media_url_0": "",
            "media_content_type_0": "",
            "message_sid": "SM_TEST_001",
            "profile_name": "",
        },
    }
    base.update(overrides)
    return base


@pytest.fixture
def supa_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    sb = MagicMock(name="supabase_mock")
    monkeypatch.setattr(main, "supabase", sb)
    monkeypatch.setattr(worker, "supabase", sb)
    return sb


@pytest.fixture(autouse=True)
def reset_stop_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(worker, "_should_stop", False)
    yield
    monkeypatch.setattr(worker, "_should_stop", False)


def test_claim_returns_none_when_queue_empty(supa_mock: MagicMock) -> None:
    supa_mock.rpc.return_value.execute.return_value.data = []
    assert worker._claim_next_job() is None


def test_claim_returns_none_when_rpc_raises(supa_mock: MagicMock) -> None:
    supa_mock.rpc.return_value.execute.side_effect = RuntimeError("boom")
    assert worker._claim_next_job() is None


def test_claim_returns_first_row(supa_mock: MagicMock) -> None:
    job = _build_job()
    supa_mock.rpc.return_value.execute.return_value.data = [job]
    assert worker._claim_next_job() == job


def test_process_job_calls_agent_run_for_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #3: di default i job passano per agent.run_for_job, non per il legacy impl."""
    mock_run = MagicMock(return_value={"status": "ok", "phase": "COLLECTING_ANAMNESIS"})
    mock_legacy = MagicMock()
    monkeypatch.setattr(agent, "run_for_job", mock_run)
    monkeypatch.setattr(worker.agent, "run_for_job", mock_run)
    monkeypatch.setattr(worker, "_process_message_impl", mock_legacy)
    monkeypatch.setattr(worker, "USE_LEGACY_PIPELINE", False)

    worker._process_job(_build_job())

    mock_run.assert_called_once()
    payload = mock_run.call_args.args[0]
    assert payload["body"] == "Ho mal di testa"
    assert payload["from_number"] == "+393331234567"
    assert mock_legacy.call_count == 0


def test_process_job_raises_on_agent_error_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Se l'agent ritorna status='error', il worker deve sollevare (retry/dead-letter)."""
    monkeypatch.setattr(
        worker.agent,
        "run_for_job",
        MagicMock(return_value={"status": "error", "reason": "paziente_not_found"}),
    )
    monkeypatch.setattr(worker, "USE_LEGACY_PIPELINE", False)

    with pytest.raises(RuntimeError):
        worker._process_job(_build_job())


def test_process_job_legacy_path_when_flag_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WORKER_USE_LEGACY=1 ripristina il path sincrono di main._process_message_impl."""
    mock_legacy = MagicMock()
    mock_agent = MagicMock()
    monkeypatch.setattr(worker, "_process_message_impl", mock_legacy)
    monkeypatch.setattr(worker.agent, "run_for_job", mock_agent)
    monkeypatch.setattr(worker, "USE_LEGACY_PIPELINE", True)

    worker._process_job(_build_job())

    mock_legacy.assert_called_once()
    kw = mock_legacy.call_args.kwargs
    assert kw["body"] == "Ho mal di testa"
    assert mock_agent.call_count == 0


def test_process_job_raises_on_unknown_kind() -> None:
    with pytest.raises(ValueError):
        worker._process_job(_build_job(kind="other"))


def test_mark_done_updates_status(supa_mock: MagicMock) -> None:
    worker._mark_done("job-abc")
    update_call = supa_mock.table.return_value.update
    update_call.assert_called_once()
    payload = update_call.call_args.args[0]
    assert payload["status"] == "done"
    assert payload["finished_at"]
    assert payload["error"] is None


def test_mark_failed_reschedules_under_max(supa_mock: MagicMock) -> None:
    worker._mark_failed_or_dead("job-1", attempts=2, max_attempts=5, err="boom")
    update_payload = supa_mock.table.return_value.update.call_args.args[0]
    assert update_payload["status"] == "pending"
    assert update_payload["error"].startswith("boom")
    assert "available_at" in update_payload
    assert "finished_at" not in update_payload


def test_mark_failed_marks_dead_at_max(supa_mock: MagicMock) -> None:
    worker._mark_failed_or_dead("job-1", attempts=5, max_attempts=5, err="boom")
    update_payload = supa_mock.table.return_value.update.call_args.args[0]
    assert update_payload["status"] == "dead"
    assert update_payload["error"].startswith("boom")
    assert update_payload["finished_at"]


def test_main_loop_processes_one_job_and_stops(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Lascia che il loop pesca un job, lo processa, poi simula un secondo claim
    vuoto e fa scattare lo shutdown durante lo sleep. Verifica che il job sia
    stato marcato done.
    """
    job = _build_job()
    rpc_calls = {"n": 0}

    def fake_rpc_execute():
        rpc_calls["n"] += 1
        out = MagicMock()
        out.data = [job] if rpc_calls["n"] == 1 else []
        return out

    supa_mock.rpc.return_value.execute.side_effect = fake_rpc_execute

    mock_impl = MagicMock(return_value={"status": "ok", "phase": "COLLECTING_ANAMNESIS"})
    monkeypatch.setattr(worker.agent, "run_for_job", mock_impl)
    monkeypatch.setattr(worker, "USE_LEGACY_PIPELINE", False)

    def fake_sleep(_seconds: float) -> None:
        worker._should_stop = True

    monkeypatch.setattr(worker.time, "sleep", fake_sleep)

    worker.main_loop()

    mock_impl.assert_called_once()
    # 1 done + 0 fail
    update_calls = supa_mock.table.return_value.update.call_args_list
    statuses = [c.args[0].get("status") for c in update_calls]
    assert "done" in statuses
    assert "dead" not in statuses
    assert "pending" not in [
        s for s in statuses if s == "pending"
    ]  # nessun reschedule

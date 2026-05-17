"""
MedFlow Background Worker (PR #2).

Loop di polling che consuma la coda `public.jobs`. Vive nello stesso repo del
backend FastAPI e importa direttamente `_process_message_impl` da `main.py`,
condividendo il client Supabase service_role e quello OpenAI.

Architettura:
- claim atomico tramite RPC `claim_one_job()` (FOR UPDATE SKIP LOCKED su Postgres),
  cosi' piu' worker possono girare in parallelo senza race.
- success: status='done', finished_at=now.
- failure: se attempts < max_attempts -> status='pending', available_at = now +
  backoff esponenziale (con cap). Se attempts >= max_attempts -> status='dead'.
- shutdown soft su SIGINT/SIGTERM: termina il job corrente, poi esce.

Avvio (Render Background Worker o locale):
    python worker.py
"""
from __future__ import annotations

import os
import signal
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from main import _process_message_impl, supabase

POLL_INTERVAL_S: float = float(os.getenv("WORKER_POLL_INTERVAL_S", "2.0"))
BACKOFF_BASE_S: float = float(os.getenv("WORKER_BACKOFF_BASE_S", "10.0"))
BACKOFF_CAP_S: float = float(os.getenv("WORKER_BACKOFF_CAP_S", "3600.0"))

_should_stop = False


def _handle_signal(signum: int, _frame: Any) -> None:
    global _should_stop
    print(
        f"[worker] segnale {signum} ricevuto, shutdown soft dopo il job corrente.",
        flush=True,
    )
    _should_stop = True


signal.signal(signal.SIGINT, _handle_signal)
try:
    signal.signal(signal.SIGTERM, _handle_signal)
except (AttributeError, ValueError):
    # SIGTERM non e' disponibile su Windows (CTRL_BREAK_EVENT si').
    pass


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _claim_next_job() -> dict | None:
    """
    Estrae atomicamente il prossimo job pending pronto.
    Ritorna il dict del job o None se la coda e' vuota / errore.
    """
    if not supabase:
        return None
    try:
        resp = supabase.rpc("claim_one_job", {}).execute()
        data = getattr(resp, "data", None) or []
        if not data:
            return None
        return data[0]
    except Exception as e:
        print(f"[worker] ERRORE claim_one_job: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return None


def _process_job(job: dict) -> None:
    """Dispatch del job in base a `kind`. Solleva su errore (loop gestisce retry)."""
    kind = job.get("kind") or "process_message"
    payload = job.get("payload") or {}
    if kind != "process_message":
        raise ValueError(f"job kind sconosciuto: {kind!r}")

    _process_message_impl(
        from_number=payload.get("from_number", "") or "",
        body=payload.get("body", "") or "",
        num_media=int(payload.get("num_media") or 0),
        media_url_0=payload.get("media_url_0", "") or "",
        media_content_type_0=payload.get("media_content_type_0", "") or "",
        message_sid=payload.get("message_sid", "") or "",
        profile_name=payload.get("profile_name", "") or "",
    )


def _mark_done(job_id: str) -> None:
    if not supabase:
        return
    try:
        supabase.table("jobs").update(
            {"status": "done", "finished_at": _utcnow_iso(), "error": None}
        ).eq("id", job_id).execute()
    except Exception as e:
        print(f"[worker] ERRORE mark_done job={job_id}: {e}", flush=True)
        traceback.print_exc()


def _mark_failed_or_dead(
    job_id: str, attempts: int, max_attempts: int, err: str
) -> None:
    if not supabase:
        return
    is_dead = attempts >= max_attempts
    short_err = (err or "")[:1000]
    if is_dead:
        update = {
            "status": "dead",
            "error": short_err,
            "finished_at": _utcnow_iso(),
        }
    else:
        backoff = min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** max(0, attempts - 1)))
        next_available = datetime.now(timezone.utc) + timedelta(seconds=backoff)
        update = {
            "status": "pending",
            "error": short_err,
            "available_at": next_available.isoformat(),
        }
    try:
        supabase.table("jobs").update(update).eq("id", job_id).execute()
    except Exception as e:
        print(
            f"[worker] ERRORE mark_failed_or_dead job={job_id}: {type(e).__name__}: {e}",
            flush=True,
        )
        traceback.print_exc()


def main_loop() -> None:
    print(
        f"[worker] avvio loop. poll={POLL_INTERVAL_S}s, backoff_base={BACKOFF_BASE_S}s, "
        f"backoff_cap={BACKOFF_CAP_S}s.",
        flush=True,
    )
    while not _should_stop:
        job = _claim_next_job()
        if job is None:
            time.sleep(POLL_INTERVAL_S)
            continue

        job_id = str(job.get("id"))
        attempts = int(job.get("attempts") or 0)
        max_attempts = int(job.get("max_attempts") or 5)
        message_sid = job.get("message_sid") or "n/a"
        print(
            f"[worker] start job={job_id} attempts={attempts}/{max_attempts} "
            f"message_sid={message_sid}",
            flush=True,
        )
        try:
            _process_job(job)
            _mark_done(job_id)
            print(f"[worker] done job={job_id}.", flush=True)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print(
                f"[worker] FAIL job={job_id} attempts={attempts}/{max_attempts}: {err}",
                flush=True,
            )
            traceback.print_exc()
            _mark_failed_or_dead(job_id, attempts, max_attempts, err)
    print("[worker] shutdown completato.", flush=True)


if __name__ == "__main__":
    main_loop()

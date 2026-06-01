"""
Backfill dell'indice RAG del fascicolo (`anamnesi_documenti`).

Indicizza tutto il contenuto testuale gia' presente in `richieste` e
`conversazioni`, cosi' la consultazione del fascicolo lato medico
("Interroga il fascicolo") puo' raggiungere la storia esistente, non solo i
referti/sintesi prodotti dall'agent in avanti. Idempotente: rilanciabile senza
duplicare (salta i source_id gia' indicizzati).

Uso:
    python backfill_index.py                 # tutti i pazienti
    python backfill_index.py <paziente_id>   # un solo paziente

Prerequisito: la migrazione `web-app/sql/fix_anamnesi_documenti_rebuild.sql`
(tabella + RPC corrette) deve essere stata applicata in Supabase.
"""
from __future__ import annotations

import sys

import agent


def main() -> None:
    paziente_id = sys.argv[1].strip() if len(sys.argv) > 1 else None
    target = paziente_id or "TUTTI i pazienti"
    print(f"[backfill] avvio indicizzazione fascicolo per: {target}", flush=True)
    stats = agent.backfill_fascicolo(paziente_id)
    print(f"[backfill] completato: {stats}", flush=True)


if __name__ == "__main__":
    main()

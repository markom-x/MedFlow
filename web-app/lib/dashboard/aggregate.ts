import type { PatientProfile, PazienteNested, RichiestaRow } from "./types";
import { cleanPhone, needsAttention, patientDisplayName } from "./format";
import { AGENT_SUMMARY_MARKER } from "./constants";

export type PatientBucket = {
  profile: PatientProfile;
  requests: RichiestaRow[];
};

function normalizePaziente(
  row: RichiestaRow
): PazienteNested | null {
  const p = row.pazienti;
  if (!p) return null;
  if (Array.isArray(p)) return p[0] ?? null;
  return p;
}

export function groupRichiesteByPatient(rows: RichiestaRow[]): Map<string, PatientBucket> {
  const map = new Map<string, PatientBucket>();

  for (const row of rows) {
    const paziente = normalizePaziente(row);
    const pazienteId =
      (paziente?.id != null ? String(paziente.id) : null) ??
      (row.paziente_id != null && String(row.paziente_id).trim() !== ""
        ? String(row.paziente_id)
        : null);

    if (!pazienteId) continue;

    const existing = map.get(pazienteId);
    if (!existing) {
      const phoneClean = paziente ? cleanPhone(paziente.telefono) : "—";
      const nomeDisplay = paziente
        ? patientDisplayName(paziente.nome, phoneClean)
        : `Paziente ${pazienteId.slice(0, 8)}…`;

      map.set(pazienteId, {
        profile: {
          id: pazienteId,
          nomeRaw: paziente?.nome ?? null,
          nomeDisplay,
          telefono: phoneClean,
          notePrivate: paziente?.note_private ?? null,
        },
        requests: [row],
      });
      continue;
    }

    existing.requests.push(row);

    if (paziente) {
      const phoneClean = cleanPhone(paziente.telefono);
      if (phoneClean && phoneClean !== "—") {
        existing.profile.telefono = phoneClean;
      }
      if (paziente.nome?.trim()) {
        existing.profile.nomeRaw = paziente.nome;
        existing.profile.nomeDisplay = patientDisplayName(
          paziente.nome,
          phoneClean
        );
      }
      const np = paziente.note_private;
      if (np != null && String(np).length > 0) {
        existing.profile.notePrivate = np;
      }
    }
  }

  return map;
}

export function sortPatientIds(
  buckets: Map<string, PatientBucket>
): string[] {
  return [...buckets.keys()].sort((a, b) => {
    const ba = buckets.get(a)!;
    const bb = buckets.get(b)!;
    const pa = needsAttention(ba.requests) ? 0 : 1;
    const pb = needsAttention(bb.requests) ? 0 : 1;
    if (pa !== pb) return pa - pb;
    if (bb.requests.length !== ba.requests.length) {
      return bb.requests.length - ba.requests.length;
    }
    return ba.profile.nomeDisplay.localeCompare(bb.profile.nomeDisplay, "it", {
      sensitivity: "base",
    });
  });
}

export function lastMessagePreview(requests: RichiestaRow[]): string {
  const sorted = [...requests].sort(
    (x, y) =>
      new Date(y.created_at).getTime() - new Date(x.created_at).getTime()
  );
  // Skip the AI clinical-summary rows: they are not chat messages.
  const lastMessage = sorted.find(
    (r) => (r.messaggio_originale ?? "").trim() !== AGENT_SUMMARY_MARKER
  );
  if (lastMessage?.url_media?.trim()) {
    const leaf =
      lastMessage.url_media.split("/").pop()?.trim() ||
      lastMessage.url_media.trim();
    const max = 56;
    const name = leaf.length > max ? `${leaf.slice(0, max)}…` : leaf;
    return `📎 ${name}`;
  }
  const raw = lastMessage?.messaggio_originale?.trim();
  if (!raw) return "No messages";
  const max = 72;
  return raw.length > max ? `${raw.slice(0, max)}…` : raw;
}

export function latestClinicalSummary(requests: RichiestaRow[]): string | null {
  const sorted = [...requests].sort(
    (x, y) =>
      new Date(y.created_at).getTime() - new Date(x.created_at).getTime()
  );
  for (const r of sorted) {
    const s = r.riassunto_clinico?.trim();
    if (s) return s;
  }
  return null;
}

/** Structured AI synthesis (dati_clinici) from the most recent summary row. */
export function latestClinicalData(
  requests: RichiestaRow[]
): RichiestaRow["dati_clinici"] | null {
  const sorted = [...requests].sort(
    (x, y) =>
      new Date(y.created_at).getTime() - new Date(x.created_at).getTime()
  );
  for (const r of sorted) {
    const d = r.dati_clinici;
    if (d && typeof d === "object") return d;
  }
  return null;
}

/** Most recent finalized request (carrying a clinical summary). */
export function latestFinalizedRequest(
  requests: RichiestaRow[]
): RichiestaRow | null {
  const sorted = [...requests].sort(
    (x, y) =>
      new Date(y.created_at).getTime() - new Date(x.created_at).getTime()
  );
  for (const r of sorted) {
    if (r.riassunto_clinico?.trim()) return r;
  }
  return null;
}

import { MEDICO_FILE_SENT, MEDICO_MSG_PREFIX } from "./constants";

/** Backend placeholder when there is only an attachment without a caption (e.g. an image). */
export function isAllegatoMultimedialePlaceholder(text: string): boolean {
  const t = text.trim();
  return t === "[Media attachment]" || t === "[Allegato Multimediale]";
}

/** Text shown in the bubble (without the operator prefix for doctor messages). */
export function bubbleMessageText(raw: string, isMedico: boolean): string {
  const t = raw.trim() || "[Empty message]";
  if (isMedico && t === MEDICO_FILE_SENT) {
    return "Attachment sent by the doctor";
  }
  if (isMedico && t.startsWith(MEDICO_MSG_PREFIX)) {
    return t.slice(MEDICO_MSG_PREFIX.length).trim() || "[Empty message]";
  }
  return t;
}

const AUDIO_EXTENSIONS = [
  ".ogg",
  ".oga",
  ".opus",
  ".mp3",
  ".mpeg",
  ".wav",
  ".m4a",
  ".aac",
  ".flac",
] as const;

export function urlLooksLikePdf(url: string | null | undefined): boolean {
  if (!url) return false;
  const lower = url.toLowerCase();
  const base = url.split("?")[0]?.split("#")[0]?.toLowerCase() ?? "";
  if (base.endsWith(".pdf")) return true;
  const leaf = lower.split("/").pop() ?? lower;
  if (leaf.startsWith("vocale_whatsapp")) return false;
  /** Storage paths from WhatsApp: `referto_whatsapp_*` (PDF or image referti) */
  return leaf.startsWith("referto_whatsapp");
}

export function urlLooksLikeAudio(url: string | null | undefined): boolean {
  if (!url) return false;
  const lower = url.toLowerCase();
  /** Legacy: URL pubblici col segmento `vocali`; path relativi Twilio: prefisso file. */
  if (lower.includes("vocali")) return true;
  const leaf = lower.split("/").pop() ?? lower;
  if (leaf.startsWith("vocale_whatsapp")) return true;
  const base = url.split("?")[0]?.split("#")[0]?.toLowerCase() ?? "";
  return AUDIO_EXTENSIONS.some((ext) => base.endsWith(ext));
}

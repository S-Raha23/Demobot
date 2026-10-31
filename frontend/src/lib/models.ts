// The model badge registry: one accent colour per Meta model (docs/07 "Design language").

export type ModelKey = "spark" | "spark-open" | "sam" | "wonder" | "voice" | "image" | "local";

export interface ModelInfo {
  key: ModelKey;
  label: string;
  long: string;
  color: string; // accent
  openWeight: boolean;
}

export const MODELS: Record<ModelKey, ModelInfo> = {
  spark: { key: "spark", label: "Spark 1.3", long: "Muse Spark 1.3", color: "#60a5fa", openWeight: false },
  "spark-open": { key: "spark-open", label: "Spark Open", long: "Muse Spark Open", color: "#2dd4bf", openWeight: true },
  sam: { key: "sam", label: "SAM 3.1", long: "SAM 3.1", color: "#fbbf24", openWeight: false },
  wonder: { key: "wonder", label: "Wonder", long: "Muse Wonder", color: "#a78bfa", openWeight: false },
  voice: { key: "voice", label: "Voice", long: "Muse Voice Transcribe", color: "#f472b6", openWeight: false },
  image: { key: "image", label: "Image", long: "Muse Image", color: "#fb7f6b", openWeight: false },
  local: { key: "local", label: "Local", long: "Local compute", color: "#94a3b8", openWeight: true },
};

const BY_ID: Record<string, { key: ModelKey; provider: string }> = {
  "muse-spark-1.3": { key: "spark", provider: "meta" },
  "meta-models/muse-spark-open-1026": { key: "spark-open", provider: "baseten" },
  "meta-models/Muse-Spark-Open-816B-A42B": { key: "spark-open", provider: "modal" },
  "sam-3.1": { key: "sam", provider: "meta" },
  "muse-wonder-1.0": { key: "wonder", provider: "meta" },
  "muse-voice-transcribe-1.0": { key: "voice", provider: "meta" },
  "muse-image-1.0": { key: "image", provider: "meta" },
};

export function modelKey(id: string | null | undefined): ModelKey {
  if (!id) return "local";
  const hit = BY_ID[id];
  if (hit) return hit.key;
  const s = id.toLowerCase();
  if (s.includes("spark-open") || s.includes("spark_open")) return "spark-open";
  if (s.includes("spark")) return "spark";
  if (s.includes("sam")) return "sam";
  if (s.includes("wonder")) return "wonder";
  if (s.includes("voice") || s.includes("transcribe")) return "voice";
  if (s.includes("image")) return "image";
  return "local";
}

export function modelInfo(id: string | null | undefined): ModelInfo {
  return MODELS[modelKey(id)];
}

export function providerOf(id: string | null | undefined, provider?: string | null): string {
  if (provider) return provider;
  return (id && BY_ID[id]?.provider) || "local";
}

export const PROVIDER_LABEL: Record<string, string> = {
  meta: "Meta",
  baseten: "Baseten",
  modal: "Modal",
  local: "Local",
};

export function providerLabel(p: string | null | undefined): string {
  if (!p) return "Local";
  return PROVIDER_LABEL[p] ?? p[0].toUpperCase() + p.slice(1);
}

/** Models each stage is expected to use (shown dimmed before a stage runs). */
export const STAGE_MODELS: Record<string, { id: string; provider: string }[]> = {
  ingest: [],
  calibrate: [],
  listen: [{ id: "muse-voice-transcribe-1.0", provider: "meta" }],
  watch: [
    { id: "muse-spark-1.3", provider: "meta" },
    { id: "meta-models/Muse-Spark-Open-816B-A42B", provider: "modal" },
  ],
  perceive: [{ id: "sam-3.1", provider: "meta" }],
  ground: [],
  twin_build: [],
  program: [{ id: "muse-wonder-1.0", provider: "meta" }],
  verify: [
    { id: "sam-3.1", provider: "meta" },
    { id: "meta-models/muse-spark-open-1026", provider: "baseten" },
  ],
  stress: [{ id: "meta-models/muse-spark-open-1026", provider: "baseten" }],
  harden: [{ id: "muse-wonder-1.0", provider: "meta" }],
  card: [{ id: "muse-image-1.0", provider: "meta" }],
};

export const STAGE_LABEL: Record<string, string> = {
  ingest: "Ingest",
  calibrate: "Calibrate",
  listen: "Listen",
  watch: "Watch",
  perceive: "Perceive",
  ground: "Ground",
  twin_build: "Twin",
  program: "Program",
  verify: "Verify",
  stress: "Stress",
  harden: "Harden",
  card: "Card",
  supervise: "Supervise",
  correct: "Correct",
};

/** A sentence for the "what is the AI doing now" line, by stage. */
export const STAGE_DOING: Record<string, string> = {
  ingest: "Reading the clip and picking keyframes",
  calibrate: "Finding the four markers and measuring the table",
  listen: "Transcribing your narration",
  watch: "Watching the demo to understand the intent",
  perceive: "Tracking every object and your hand",
  ground: "Measuring every move in centimetres",
  twin_build: "Building the digital twin",
  program: "Writing and debugging the robot program",
  verify: "Checking the result with the same eyes",
  stress: "Red team is attacking the program",
  harden: "Hardening the program against failures",
  card: "Illustrating the skill card",
  supervise: "Supervisor is deciding how to recover",
  correct: "Applying your correction",
};

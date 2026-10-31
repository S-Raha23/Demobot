import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { blobToWav } from "../lib/wav";
import { Icon } from "./Icon";
import { Spinner } from "./ui";

export function CorrectionDock({ runId, enabled, onNotice }: { runId: string; enabled: boolean; onNotice: (msg: string) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [rec, setRec] = useState(false);
  const mr = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const nav = useNavigate();

  const send = async (body: FormData | { text: string }) => {
    setBusy(true);
    try {
      const r = await api.correct(runId, body);
      nav(`/run/${r.run_id}`);
    } catch (e) {
      const live = e instanceof ApiError && (e.status === 404 || e.status === 405);
      onNotice(live ? "Corrections need the live backend. This server only replays recorded runs." : e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    if (!enabled || busy) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const m = new MediaRecorder(stream);
      chunks.current = [];
      m.ondataavailable = (e) => chunks.current.push(e.data);
      m.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks.current, { type: m.mimeType });
        try {
          const wav = await blobToWav(blob);
          const f = new FormData();
          f.append("audio", wav, "correction.wav");
          await send(f);
        } catch {
          onNotice("Could not read the recording.");
        }
      };
      m.start();
      mr.current = m;
      setRec(true);
    } catch {
      onNotice("Microphone permission is needed to talk to it.");
    }
  };
  const stop = () => {
    if (mr.current && mr.current.state !== "inactive") mr.current.stop();
    mr.current = null;
    setRec(false);
  };

  return (
    <form
      className="flex items-center gap-2 border-t border-ink-700/60 p-2.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) send({ text: text.trim() });
      }}
    >
      <button
        type="button"
        disabled={!enabled || busy}
        onPointerDown={start}
        onPointerUp={stop}
        onPointerLeave={() => rec && stop()}
        className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition ${
          rec ? "bg-voice text-ink-950 shadow-[0_0_24px_rgba(244,114,182,0.6)]" : "bg-voice/15 text-voice ring-1 ring-inset ring-voice/40 hover:bg-voice/25"
        } disabled:opacity-40`}
        title="Hold to talk: correct it in English, Hindi or Bengali"
        aria-label="Hold to talk"
      >
        {rec && <span className="absolute inset-0 animate-ping rounded-full bg-voice/40" />}
        <Icon name="mic" size={16} />
      </button>
      <input
        value={text}
        disabled={!enabled || busy}
        onChange={(e) => setText(e.target.value)}
        placeholder={enabled ? "Correct it: “no, the eraser goes left of the mug”" : "Corrections open when the run finishes"}
        className="h-9 min-w-0 flex-1 rounded-lg bg-ink-850 px-3 text-[12.5px] text-ink-100 placeholder:text-ink-500 ring-1 ring-inset ring-ink-600/70 outline-none focus:ring-voice/50 disabled:opacity-60"
      />
      <button type="submit" className="btn !h-9 !px-3" disabled={!enabled || busy || !text.trim()}>
        {busy ? <Spinner size={13} /> : <Icon name="arrow" size={14} />}
      </button>
    </form>
  );
}

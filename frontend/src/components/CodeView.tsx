import { useEffect, useState } from "react";
import { highlightPython } from "../lib/highlight";

/** Read-only code with line numbers; `stream` types it in (Wonder's code "streaming"). */
export function CodeView({ code, stream = false, maxHeight }: { code: string; stream?: boolean; maxHeight?: number }) {
  const [n, setN] = useState(stream ? 0 : code.length);
  useEffect(() => {
    if (!stream) {
      setN(code.length);
      return;
    }
    setN(0);
    const total = code.length;
    const t0 = performance.now();
    const dur = Math.min(2200, 300 + total * 6);
    let raf = 0;
    const step = () => {
      const f = Math.min(1, (performance.now() - t0) / dur);
      setN(Math.round(total * f));
      if (f < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [code, stream]);
  const shown = code.slice(0, n);
  const lines = shown.split("\n");
  const typing = n < code.length;
  return (
    <div className="scroll-thin code overflow-auto rounded-lg bg-ink-950/70 py-2 ring-1 ring-inset ring-ink-700/60" style={{ maxHeight }}>
      {lines.map((l, i) => (
        <div key={i} className="flex px-3 hover:bg-white/[0.02]">
          <span className="num mr-4 w-6 shrink-0 select-none text-right text-ink-500">{i + 1}</span>
          <span className={`whitespace-pre text-ink-100 ${typing && i === lines.length - 1 ? "caret" : ""}`}>
            {highlightPython(l).map((t, k) => (
              <span key={k} className={t.c}>
                {t.t}
              </span>
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}

export function DiffView({ diff, maxHeight }: { diff: string; maxHeight?: number }) {
  const lines = diff.split("\n").filter((l, i, a) => !(i === a.length - 1 && l === ""));
  return (
    <div className="scroll-thin code overflow-auto rounded-lg bg-ink-950/70 py-2 ring-1 ring-inset ring-ink-700/60" style={{ maxHeight }}>
      {lines.map((l, i) => {
        const add = l.startsWith("+") && !l.startsWith("+++");
        const del = l.startsWith("-") && !l.startsWith("---");
        const hunk = l.startsWith("@@");
        const head = l.startsWith("+++") || l.startsWith("---");
        return (
          <div
            key={i}
            className={`flex whitespace-pre px-3 ${add ? "bg-ok/[0.09] text-ok" : del ? "bg-bad/[0.09] text-bad/90" : hunk ? "text-spark/80" : head ? "text-ink-400" : "text-ink-200"}`}
          >
            <span className="mr-3 w-3 shrink-0 select-none opacity-70">{add ? "+" : del ? "−" : ""}</span>
            {add || del ? l.slice(1) : l}
          </div>
        );
      })}
    </div>
  );
}

import { useEffect, useState } from "react";
import { api, type Toolkit as ToolkitT } from "../lib/api";
import { CodeView } from "./CodeView";
import { Icon } from "./Icon";
import { Pill } from "./ui";

/** The robot's skills: built-in primitives and those DemoBot invented itself (Skill Forge, docs/11 F1). */
export function Toolkit() {
  const [tk, setTk] = useState<ToolkitT | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    api.toolkit().then(setTk).catch(() => setTk(null));
  }, []);
  if (!tk || !tk.enabled) return null;
  return (
    <section className="mx-auto max-w-[1560px] px-5 pb-12 md:px-8" data-testid="toolkit">
      <div className="mb-1 flex flex-wrap items-baseline gap-3">
        <div className="eyebrow">Toolkit</div>
        <span className="text-[12px] text-ink-400">skill API v{tk.skill_api_version}</span>
      </div>
      <h2 className="text-[26px] font-semibold tracking-tight text-ink-50">
        {tk.built_in.length} built in{tk.invented.length ? `, ${tk.invented.length} invented by DemoBot` : ""}
      </h2>
      <div className="mt-1 text-[13px] text-ink-400">When no combination of its skills can do a task, DemoBot writes a new one, tests it on randomised layouts and keeps it only if it passes 9/10.</div>
      <div className="mt-4 flex flex-wrap gap-2">
        {tk.built_in.map((n) => (
          <span key={n} className="rounded-lg bg-ink-800 px-2.5 py-1.5 font-mono text-[12.5px] text-ink-200 ring-1 ring-inset ring-ink-600">
            {n} <span className="ml-1 font-sans text-[10.5px] text-ink-400">built in</span>
          </span>
        ))}
        {tk.invented.map((s) => (
          <button key={s.name} type="button" onClick={() => setOpen(open === s.name ? null : s.name)}
            className="rounded-lg bg-wonder/10 px-2.5 py-1.5 font-mono text-[12.5px] text-wonder ring-1 ring-inset ring-wonder/35 hover:bg-wonder/20">
            {s.name}{" "}
            <span className="ml-1 font-sans text-[10.5px] text-ink-300">invented by DemoBot, {new Date(s.promoted_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</span>
          </button>
        ))}
      </div>
      {tk.invented
        .filter((s) => s.name === open)
        .map((s) => (
          <div key={s.name} className="panel mt-3 overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 p-3.5">
              <span className="font-mono text-[13px] text-wonder">{s.signature}</span>
              <Pill tone={s.pass_rate >= 0.9 ? "ok" : "warn"}>
                <Icon name="check" size={11} /> {Math.round(s.pass_rate * 100)}% on fresh layouts
              </Pill>
              {s.regression?.checked != null && <Pill tone="ok">regression gate: {s.regression.checked} runs, none worse</Pill>}
            </div>
            <div className="px-3.5 pb-2 text-[12.5px] text-ink-300">{s.doc || s.purpose}</div>
            <div className="px-3.5 pb-3 text-[12px] text-ink-400">Why: {s.evidence}</div>
            {s.grid && s.grid.length > 0 && (
              <div className="flex gap-1 px-3.5 pb-3">
                {s.grid.map((c) => (
                  <span key={c.layout} title={c.layout} className={`h-4 w-4 rounded ${c.passed ? "bg-ok/70" : "bg-bad/70"}`} />
                ))}
              </div>
            )}
            <CodeView code={s.code} />
          </div>
        ))}
    </section>
  );
}

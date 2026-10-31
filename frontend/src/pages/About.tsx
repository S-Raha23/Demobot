import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Donut } from "../components/Donut";
import { Icon } from "../components/Icon";
import { ModelBadge } from "../components/ModelBadge";
import { TopNav } from "../components/TopNav";
import { Pill, Stat } from "../components/ui";
import { api, type CostsResponse } from "../lib/api";
import { usd } from "../lib/format";
import { modelInfo, providerLabel, providerOf } from "../lib/models";

const ROLES: { model: string; provider?: string; job: string; why: string }[] = [
  { model: "muse-spark-1.3", job: "Watches the demo video with the transcript and writes the TaskSpec: objects, timed steps, a checkable goal, a generalisation rule.", why: "Native video understanding and structured output" },
  { model: "muse-voice-transcribe-1.0", job: "Transcribes narration in the clip and spoken corrections (English, Hindi, Bengali).", why: "Multilingual speech-to-text" },
  { model: "sam-3.1", job: "Text-prompted masks and persistent track IDs for every object and the hand; also segments the simulator's render.", why: "Pixel-precise, identity-preserving tracks" },
  { model: "muse-wonder-1.0", job: "Writes the robot program and debugs it with simulator tool calls; hardens it; applies corrections as code edits.", why: "Long-horizon agentic coding" },
  { model: "meta-models/muse-spark-open-1026", provider: "baseten", job: "Supervisor, six-persona red-team swarm, and the judge that compares real and twin.", why: "Open weights, cheap and fast at volume" },
  { model: "meta-models/Muse-Spark-Open-816B-A42B", provider: "modal", job: "An independent second watch of the clip; disagreement triggers Wonder arbitration.", why: "Open-weight video path, measured agreement" },
  { model: "muse-image-1.0", job: "Illustrated skill cards anchored on the real final frame.", why: "Accurate text rendering, anchored editing" },
];

export default function About() {
  const [costs, setCosts] = useState<CostsResponse | null>(null);
  const [evalMd, setEvalMd] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    api.costs().then(setCosts).catch(() => setCosts({ ledger: null, runs: [] }));
    api
      .evalResults()
      .then((r) => setEvalMd(r.markdown))
      .catch(() => setEvalMd(null));
  }, []);

  const agg = useMemo(() => {
    const byModel: Record<string, number> = {};
    let total = 0;
    let open = 0;
    let fixtures = 0;
    for (const r of costs?.runs ?? []) {
      total += r.total_usd;
      open += r.total_usd * r.open_weight_share;
      if (r.fixture) fixtures++;
      for (const [m, v] of Object.entries(r.by_model)) byModel[m] = (byModel[m] ?? 0) + v;
    }
    const n = costs?.runs.length ?? 0;
    return { byModel, total, open, perSkill: n ? total / n : 0, n, fixtures };
  }, [costs]);

  const ledgerModels = Object.entries(costs?.ledger?.by_model ?? {}).sort((a, b) => b[1].usd - a[1].usd);
  const ledgerTotal = ledgerModels.reduce((a, [, r]) => a + r.usd, 0);
  const maxRun = Math.max(1e-9, ...Object.values(agg.byModel));

  return (
    <div className="min-h-full">
      <TopNav />
      <main className="mx-auto max-w-[1400px] space-y-10 px-5 py-10 md:px-8">
        <div>
          <div className="eyebrow">Costs &amp; about</div>
          <h1 className="mt-1 text-[34px] font-semibold tracking-tight text-ink-50">What it costs to learn a skill</h1>
          <p className="mt-2 max-w-3xl text-[14px] text-ink-300">Every model call goes through one gateway that caches, prices, caps and ledgers it. Every number on this page comes from those files.</p>
        </div>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1.4fr_1fr]">
          <div className="panel p-5">
            <div className="flex flex-wrap gap-10">
              <Stat label="Cost per learned skill" value={usd(agg.perSkill, 3)} sub={`mean over ${agg.n} run${agg.n === 1 ? "" : "s"}${agg.fixtures ? ` (${agg.fixtures} synthetic, simulated prices)` : ""}`} />
              <Stat label="Open-weight share" value={`${agg.total ? Math.round((agg.open / agg.total) * 100) : 0}%`} sub="of run spend on Spark Open" color="#2dd4bf" />
              <Stat label="Runs" value={agg.n} />
            </div>
            <div className="eyebrow mb-2 mt-6">Spend per model, across runs</div>
            <div className="space-y-2">
              {Object.entries(agg.byModel)
                .sort((a, b) => b[1] - a[1])
                .map(([m, v]) => (
                  <div key={m} className="grid grid-cols-[180px_1fr_80px] items-center gap-3">
                    <ModelBadge model={m} provider={providerOf(m)} size="xs" />
                    <div className="h-2.5 overflow-hidden rounded-full bg-ink-800">
                      <div className="h-full rounded-full" style={{ width: `${(v / maxRun) * 100}%`, background: modelInfo(m).color }} />
                    </div>
                    <span className="num text-right text-[12px] text-ink-100">{usd(v, 4)}</span>
                  </div>
                ))}
            </div>
          </div>
          <div className="panel flex flex-col gap-4 p-5">
            <div className="flex items-center gap-5">
              <Donut
                size={132}
                parts={[
                  { value: agg.open, color: "#2dd4bf", label: "open weights" },
                  { value: Math.max(0, agg.total - agg.open), color: "#33445c", label: "API models" },
                ]}
                center={`${agg.total ? Math.round((agg.open / agg.total) * 100) : 0}%`}
                sub="open weights"
              />
              <div className="text-[12.5px] text-ink-300">
                The supervisor, the red-team swarm and the judge make the most calls, and all run on <span className="font-semibold text-sparkopen">Muse Spark Open</span> (Baseten, Modal).
              </div>
            </div>
            {costs?.ledger && (
              <div>
                <div className="eyebrow mb-2">Build ledger (every paid call while building)</div>
                <div className="space-y-1">
                  {Object.entries(costs.ledger.by_provider).map(([p, r]) => (
                    <div key={p} className="flex items-center gap-2 text-[12.5px]">
                      <span className="w-20 text-ink-200">{providerLabel(p)}</span>
                      <span className="num text-ink-100">{usd(r.usd, 2)}</span>
                      <span className="num ml-auto text-[11px] text-ink-400">
                        {r.calls} calls · {r.cache_hits} cache hits
                      </span>
                    </div>
                  ))}
                  <div className="flex items-center gap-2 border-t border-ink-700/60 pt-1.5 text-[12.5px]">
                    <span className="w-20 font-semibold text-ink-100">Total</span>
                    <span className="num font-semibold text-ink-50">{usd(ledgerTotal, 2)}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="panel p-5">
          <div className="mb-3 flex items-center gap-2">
            <span className="eyebrow">Evaluation</span>
            <span className="text-[12px] text-ink-400">from eval/results.md</span>
          </div>
          {evalMd ? (
            <Markdown md={evalMd} />
          ) : evalMd === null ? (
            <div className="text-[13px] text-ink-400">The evaluation table appears here once eval/results.md has been generated.</div>
          ) : (
            <div className="shimmer h-20 rounded-lg" />
          )}
        </section>

        <section>
          <div className="eyebrow">Credits</div>
          <h2 className="mt-1 text-[24px] font-semibold tracking-tight text-ink-50">Meta's models, each where it is strongest</h2>
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
            {ROLES.map((r) => (
              <div key={r.model + (r.provider ?? "")} className="panel flex gap-3 p-4">
                <div className="mt-0.5 h-full w-1 shrink-0 rounded-full" style={{ background: modelInfo(r.model).color }} />
                <div className="min-w-0">
                  <ModelBadge model={r.model} provider={r.provider} size="sm" />
                  <div className="mt-2 text-[13px] leading-relaxed text-ink-200">{r.job}</div>
                  <div className="mt-1 text-[12px] text-ink-400">{r.why}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Note title="Built during the hackathon" icon="clock">
            DemoBot was built for the Meta Global AI Developer Hackathon (Indie track, Push the Frontier), Oct 26 – Nov 4, 2026. This repo restarts DemoBot on Oct 31, 2026, porting code from the
            author's first repo of the same event (Oct 27–30). Claude Code was the build tool; Meta's models do all of the AI work in the product.
          </Note>
          <Note title="Honest about what is real" icon="shield">
            The robot is simulated: a Franka Panda in PyBullet. DemoBot exports a robot-agnostic program; no physical robot was used. Recorded runs are labelled as replays, and synthetic fixture runs
            say that their model calls are simulated.
          </Note>
          <Note title="Related work" icon="layers">
            SeeDo (arXiv 2410.08792) turns demonstration videos into robot plans with vision-language models; Code-as-Policies writes robot policy code with language models. DemoBot adds metric
            calibration from one phone, simulator-in-the-loop synthesis, three-way verification and adversarial hardening.
          </Note>
          <Note title="Try it for free" icon="hand">
            The interactive twin never calls a paid model: the learned program runs in simulation on your layout.{" "}
            <Link to="/try" className="font-semibold text-sparkopen hover:underline">
              Open Try it →
            </Link>
          </Note>
        </section>
        <div className="flex flex-wrap gap-2">
          <Pill tone="neutral">React · three.js · urdf-loader</Pill>
          <Pill tone="neutral">FastAPI · PyBullet · OpenCV</Pill>
        </div>
      </main>
    </div>
  );
}

function Note({ title, icon, children }: { title: string; icon: string; children: ReactNode }) {
  return (
    <div className="panel p-5">
      <div className="flex items-center gap-2 text-[14px] font-semibold text-ink-50">
        <Icon name={icon} size={16} className="text-ink-300" /> {title}
      </div>
      <div className="mt-2 text-[13px] leading-relaxed text-ink-300">{children}</div>
    </div>
  );
}

/** Enough Markdown for results.md: headings, tables, lists, paragraphs, **bold**, `code`. */
function Markdown({ md }: { md: string }) {
  const blocks: ReactNode[] = [];
  const lines = md.split("\n");
  const inline = (s: string) =>
    s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((p, i) =>
      p.startsWith("**") ? (
        <b key={i} className="text-ink-50">
          {p.slice(2, -2)}
        </b>
      ) : p.startsWith("`") ? (
        <code key={i} className="rounded bg-ink-800 px-1 font-mono text-[12px]">
          {p.slice(1, -1)}
        </code>
      ) : (
        p
      ),
    );
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (l.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        if (!/^\|[\s:-|]+\|$/.test(lines[i].trim())) rows.push(lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
        i++;
      }
      i--;
      blocks.push(
        <div key={i} className="scroll-thin overflow-x-auto rounded-lg ring-1 ring-ink-700/60">
          <table className="w-full text-[12.5px]">
            <thead className="bg-ink-800/70 text-left text-ink-300">
              <tr>
                {rows[0]?.map((c, k) => (
                  <th key={k} className="px-3 py-2 font-semibold">
                    {inline(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(1).map((r, k) => (
                <tr key={k} className="border-t border-ink-700/50">
                  {r.map((c, j) => (
                    <td key={j} className={`px-3 py-1.5 ${j ? "num" : ""} text-ink-100`}>
                      {inline(c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
    } else if (/^#{1,6} /.test(l)) {
      blocks.push(
        <div key={i} className="pt-2 text-[15px] font-semibold text-ink-50">
          {inline(l.replace(/^#+ /, ""))}
        </div>,
      );
    } else if (/^[-*] /.test(l)) {
      blocks.push(
        <div key={i} className="pl-3 text-[13px] text-ink-300">
          • {inline(l.slice(2))}
        </div>,
      );
    } else if (l.trim()) {
      blocks.push(
        <p key={i} className="text-[13px] text-ink-300">
          {inline(l)}
        </p>,
      );
    }
  }
  return <div className="space-y-2">{blocks}</div>;
}

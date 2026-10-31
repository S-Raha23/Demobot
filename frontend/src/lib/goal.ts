import type { GoalClause, Selector, Step } from "./types";

export function selText(s: Selector | null | undefined, plural = false): string {
  if (!s) return "";
  if (s.names?.length) return s.names.join(" and ");
  if (s.name) return `the ${s.name}`;
  if (s.kind) return plural ? `every ${s.kind}` : `the ${s.kind}`;
  if (s.role) return plural ? `every ${s.role} object` : `the ${s.role} object`;
  return "objects";
}

export function selChip(s: Selector | null | undefined): string {
  if (!s) return "";
  if (s.names?.length) return s.names.join(", ");
  return s.name ?? (s.kind ? `kind: ${s.kind}` : s.role ? `role: ${s.role}` : "any");
}

const PRED: Record<string, string> = {
  inside: "is inside",
  left_of: "is left of",
  right_of: "is right of",
  in_front_of: "is in front of",
  behind: "is behind",
  near: "is near",
  collinear: "are lined up",
  swapped: "have swapped places",
};

export function clauseSentence(c: GoalClause): string {
  const subj = c.quant === "all" ? selText(c.select, true) : selText(c.select);
  const s = subj.charAt(0).toUpperCase() + subj.slice(1);
  if (c.pred === "collinear") return `${s} ${c.quant === "all" ? "are" : "is"} lined up${c.order_by ? ` along ${c.order_by}` : c.order ? ` in the order ${c.order.join(", ")}` : ""}.`;
  if (c.pred === "swapped") return `${s} have swapped places.`;
  if (c.pred === "near" && c.point_cm) return `${s} is within 4 cm of (${c.point_cm[0].toFixed(0)}, ${c.point_cm[1].toFixed(0)}) cm.`;
  return `${s} ${PRED[c.pred] ?? c.pred} ${selText(c.target)}.`;
}

export function clauseChips(c: GoalClause): { text: string; kind: "quant" | "sel" | "pred" | "target" }[] {
  const out: { text: string; kind: "quant" | "sel" | "pred" | "target" }[] = [
    { text: c.quant, kind: "quant" },
    { text: selChip(c.select), kind: "sel" },
    { text: c.pred.replace(/_/g, " "), kind: "pred" },
  ];
  if (c.target) out.push({ text: selChip(c.target), kind: "target" });
  if (c.point_cm) out.push({ text: `(${c.point_cm[0].toFixed(0)}, ${c.point_cm[1].toFixed(0)}) cm`, kind: "target" });
  if (c.order_by) out.push({ text: `by ${c.order_by}`, kind: "target" });
  if (c.order) out.push({ text: c.order.join(" → "), kind: "target" });
  return out;
}

export function stepSentence(s: Step): string {
  if (s.action === "place_in") return `Put the ${s.object} into the ${s.target}.`;
  if (s.action === "place_next_to") return `Place the ${s.object} ${s.relation?.replace(/_/g, " ") ?? "next to"} the ${s.target}.`;
  return `Place the ${s.object}${s.target ? ` at ${s.target}` : ""}.`;
}

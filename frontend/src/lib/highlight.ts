// A tiny Python highlighter (keywords, strings, numbers, comments, calls) for the code view.

const KW = new Set(
  "def return for in if elif else while not and or is None True False import from as with try except finally raise pass continue break lambda class yield assert del global nonlocal".split(" "),
);

export interface Tok {
  t: string;
  c?: string;
}

export function highlightPython(line: string): Tok[] {
  const out: Tok[] = [];
  const re = /(#.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)|(\s+)|(.)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line))) {
    if (m[1]) out.push({ t: m[1], c: "tok-com" });
    else if (m[2]) out.push({ t: m[2], c: "tok-str" });
    else if (m[3]) out.push({ t: m[3], c: "tok-num" });
    else if (m[4]) {
      const w = m[4];
      const next = line.slice(re.lastIndex).trimStart()[0];
      if (KW.has(w)) out.push({ t: w, c: "tok-kw" });
      else if (w === "scene" || w === "robot" || w === "self") out.push({ t: w, c: "tok-self" });
      else if (next === "(") out.push({ t: w, c: "tok-fn" });
      else out.push({ t: w });
    } else out.push({ t: m[5] ?? m[6] ?? "" });
  }
  return out;
}

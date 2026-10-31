/** A line diff (LCS) in unified style without hunk headers, for versions without a stored diff. */
export function lineDiff(a: string, b: string, nameA = "a", nameB = "b"): string {
  const A = a.replace(/\n$/, "").split("\n");
  const B = b.replace(/\n$/, "").split("\n");
  const n = A.length;
  const m = B.length;
  const L: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [`--- ${nameA}`, `+++ ${nameB}`];
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && A[i] === B[j]) {
      out.push(` ${A[i]}`);
      i++;
      j++;
    } else if (j < m && (i >= n || L[i][j + 1] >= L[i + 1][j])) out.push(`+${B[j++]}`);
    else out.push(`-${A[i++]}`);
  }
  return out.join("\n") + "\n";
}

// A small Cypher highlighter: keywords, functions, strings, numbers, $params, :Labels.
export type Tok = { t: string; c?: "kw" | "str" | "param" | "fn" | "num" | "label" };

const KW = new Set(
  ("MATCH OPTIONAL WHERE RETURN WITH UNWIND MERGE CREATE SET DELETE DETACH REMOVE ON CALL YIELD ORDER BY LIMIT SKIP " +
    "DISTINCT AS AND OR NOT IN IS NULL TRUE FALSE CASE WHEN THEN ELSE END DESC ASC EXISTS ALL ANY NONE COUNT CONTAINS STARTS ENDS").split(" "),
);
const RE = /('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")|(\$[A-Za-z_][\w]*)|(:[A-Z_][A-Za-z_]*)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][\w.]*)(?=\s*\()|([A-Za-z_]\w*)|(\s+|.)/g;

export function tokenize(src: string): Tok[] {
  const out: Tok[] = [];
  for (const m of src.matchAll(RE)) {
    const [s, str, param, label, num, fn, word] = m;
    if (str) out.push({ t: s, c: "str" });
    else if (param) out.push({ t: s, c: "param" });
    else if (label) out.push({ t: s, c: "label" });
    else if (num) out.push({ t: s, c: "num" });
    else if (fn) out.push({ t: s, c: KW.has(fn.toUpperCase()) ? "kw" : "fn" });
    else if (word) out.push({ t: s, c: KW.has(word.toUpperCase()) ? "kw" : undefined });
    else out.push({ t: s });
  }
  return out;
}

/** Break a one-line query before its main clauses so it reads like a query. */
export function pretty(cypher: string): string {
  return cypher
    .replace(/\s+(OPTIONAL MATCH|MATCH|WHERE|RETURN|WITH|UNWIND|MERGE|CREATE|SET|CALL|YIELD|ORDER BY|LIMIT|ON CREATE SET|ON MATCH SET)\b/g, "\n$1")
    .replace(/\nOPTIONAL\nMATCH/g, "\nOPTIONAL MATCH")
    .trim();
}

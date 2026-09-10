// Match Python's Unicode code point ordering; JS default order uses UTF-16 units.
export function codePointCompare(a: string, b: string): number {
  const left = Array.from(a), right = Array.from(b);
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    const delta = left[i].codePointAt(0)! - right[i].codePointAt(0)!;
    if (delta) return delta;
  }
  return left.length - right.length;
}
export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") return `{${Object.entries(value)
    .sort(([a], [b]) => codePointCompare(a, b)).map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`).join(",")}}`;
  const encoded = JSON.stringify(value);
  if (encoded === undefined) throw new Error("Not a JSON value");
  return encoded;
}

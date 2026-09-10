import { expect, it } from "vitest";
import { codePointCompare, canonicalJson } from "../lib/cross-level-canonical";
it("matches Python sorted and ensure_ascii=False serialization for BMP and supplementary characters", () => {
  expect(["🎓补充条件", "（补充条件）"].sort(codePointCompare)).toEqual(["（补充条件）", "🎓补充条件"]);
  expect(canonicalJson({ "🎓": "emoji", "（": "bmp", nested: { "🎓": 2, "（": 1 } }))
    .toBe('{"nested":{"（":1,"🎓":2},"（":"bmp","🎓":"emoji"}');
});

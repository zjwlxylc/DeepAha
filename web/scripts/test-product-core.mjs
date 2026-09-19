import assert from 'node:assert/strict';
globalThis.document={addEventListener(){}};
const {time,e}=await import('../public/product/core.js');
assert.equal(time(null),'—');
assert.equal(time('source-did-not-provide-a-date'),'时间未明确');
assert.match(time('2026-09-17T08:00:00+08:00'),/09/);
assert.equal(e('<img onerror="alert(1)">'),'&lt;img onerror=&quot;alert(1)&quot;&gt;');
console.log('Core rendering checks passed: missing/invalid/known dates and text escaping');

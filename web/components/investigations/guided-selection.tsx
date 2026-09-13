"use client";

import { useState } from "react";
import Link from "next/link";
import type { InvestigationTask } from "../../lib/investigations";
import { reviewHref } from "../../lib/guided-review";

export default function GuidedSelection({ task, queue = "" }: { task: InvestigationTask; queue?: string }) {
  const [query, setQuery] = useState("");
  const [ids, setIds] = useState<string[]>([]);
  const positions = task.binding_entities?.filter(e => e.kind === "position") ?? [];
  const units = (task.opportunities?.units ?? []) as { name: string; positions: { id: string }[] }[];
  const unitName = (id: string) => units.find(unit => unit.positions.some(p => p.id === id))?.name ?? "所属单位待核对";
  const matches = positions.filter(p => `${unitName(p.id)} ${p.name} ${p.code ?? ""}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <section className="guided-card">
    <p className="eyebrow">第 1 步，共 3 步 · 选择岗位</p>
    <h1>这次先核对哪两个岗位？</h1>
    <p>选好后，我们会逐条显示原文和要核对的内容。看不懂的地方可以标记待处理。</p>
    <label className="guided-search">搜索单位、岗位名称或编号<input value={query} onChange={e => setQuery(e.target.value)} type="search" placeholder="输入你想核对的岗位或单位" /></label>
    <div className="guided-picked" aria-live="polite"><strong>已选 {ids.length} / 2 个</strong>{ids.map(id => <button key={id} type="button" onClick={() => setIds(ids.filter(value => value !== id))}>{positions.find(p => p.id === id)?.name} · 移除</button>)}</div>
    <div className="guided-continue">{ids.length === 2 ? <Link className="button button-primary" href={reviewHref(task.task_id, ids, undefined, "facts", 0, queue)}>继续：核对这两个岗位</Link> : <button className="button button-primary" disabled>选满两个岗位后继续</button>}</div>
    <fieldset className="guided-positions"><legend>选择两个实际岗位</legend>
      {matches.slice(0, 20).map(p => <label key={p.id} className="guided-position"><input type="checkbox" checked={ids.includes(p.id)} disabled={ids.length === 2 && !ids.includes(p.id)} onChange={e => setIds(e.target.checked ? [...ids, p.id] : ids.filter(id => id !== p.id))} /><span><strong>{p.name}</strong><span>{unitName(p.id)} · 编号 {p.code ?? "原文未标明"}</span></span></label>)}
      {!matches.length ? <p role="status">没有找到对应岗位，换一个名称或单位试试。</p> : matches.length > 20 ? <p>当前显示前 20 个，请用搜索缩小范围。</p> : null}
    </fieldset>
  </section>;
}

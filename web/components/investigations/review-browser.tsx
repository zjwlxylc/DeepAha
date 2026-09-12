"use client";

import { useState, type ReactNode } from "react";

/** Filters only the view. Hidden rows retain their evidence and review state. */
export default function ReviewBrowser<T>({ items, label, searchText, needsAttention, children }: {
  items: T[]; label: string; searchText: (item: T) => string;
  needsAttention: (item: T) => boolean; children: (visible: T[]) => ReactNode;
}) {
  const [query, setQuery] = useState("");
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [page, setPage] = useState(0);
  const attentionCount = items.filter(needsAttention).length;
  const filtered = items.filter(item => (!attentionOnly || needsAttention(item))
    && searchText(item).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const pageCount = Math.max(1, Math.ceil(filtered.length / 12));
  const current = Math.min(page, pageCount - 1);
  const reset = () => { setQuery(""); setAttentionOnly(false); setPage(0); };
  return <div className="review-browser" role="group" aria-label={label}>
    <div className="review-browser-tools">
      <label>搜索{label}<input type="search" value={query} placeholder="输入名称、条件或关键词"
        onChange={event => { setQuery(event.target.value); setPage(0); }} /></label>
      <div className="review-filter-buttons">
        <button type="button" aria-pressed={!attentionOnly} onClick={() => { setAttentionOnly(false); setPage(0); }}>全部 {items.length}</button>
        <button type="button" aria-pressed={attentionOnly} onClick={() => { setAttentionOnly(true); setPage(0); }}>优先看待处理 {attentionCount}</button>
      </div>
    </div>
    <p className="field-help">筛选只改变展示范围，不会批准、删除或忽略其他内容。</p>
    {filtered.length ? children(filtered.slice(current * 12, (current + 1) * 12))
      : <div className="empty-state"><p>没有找到相符内容。可以更换关键词，或查看全部。</p><button type="button" onClick={reset}>清除筛选</button></div>}
    <nav className="review-pagination" aria-label={`${label}分页`}>
      <button type="button" disabled={current === 0} onClick={() => setPage(current - 1)}>上一页</button>
      <span role="status">共 {filtered.length} 项 · 第 {current + 1} / {pageCount} 页</span>
      <button type="button" disabled={current + 1 >= pageCount} onClick={() => setPage(current + 1)}>下一页</button>
    </nav>
  </div>;
}

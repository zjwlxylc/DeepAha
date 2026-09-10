"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { loadGroupApplicabilityAction } from "../../app/review/investigations/group-applicability-actions";
import type { GroupApplicabilityIdentity, GroupApplicabilityResult, GroupApplicabilityView } from "../../lib/group-applicability";

export default function GroupApplicability({ identity, initial }: { identity: GroupApplicabilityIdentity; initial: GroupApplicabilityResult<GroupApplicabilityView> }) {
  const [result, setResult] = useState<typeof initial | null>(initial), [busy, setBusy] = useState(false);
  const active = useRef(false);
  async function read(after: string | null = null) {
    if (active.current) return;
    active.current = true; setBusy(true);
    const expected = result?.ok ? result.value.context_hash : null;
    setResult(null);
    try {
      const next = await loadGroupApplicabilityAction(identity, after);
      setResult(after && next.ok && next.value.context_hash !== expected ? { ok: false, error: "上下文已变化，旧内容已隐藏，请重新读取首页。" } : next);
    } catch { setResult({ ok: false, error: "当前读取失败，旧内容已隐藏。" }); }
    finally { active.current = false; setBusy(false); }
  }
  const view = result?.ok ? result.value : null;
  const facts = view?.source_review.result.preview.result.fact_review.result;
  const source = facts?.group_source;
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs"><Link href={`/review/investigations/${identity.task_id}/unit-plans/${identity.target_plan_id}`}>返回岗位条件快照</Link></nav>
    <h1>组规则与岗位依据核对</h1>
    <aside className="fixture-notice">仅核对来源与成员关系。岗位适用尚未裁决，不自动继承规则，整体资格仍不确定。</aside>
    <button className="button button-secondary" disabled={busy} onClick={() => void read()}>{busy ? "正在核对…" : "重新读取当前上下文"}</button>
    {result && !result.ok ? <section role="alert" className="human-test-panel"><h2>当前上下文不可用</h2><p>{result.error}</p></section> : null}
    {view && facts && source ? <>
      <section className="human-test-panel"><h2>{source.group_identity.label} → {view.context.target_entity_id}</h2>
        <p>组版本 {source.group_identity.version} · 岗位版本 {view.context.target.unit_version} · 尚未裁决</p>
        <p>原组字段 {facts.rows.length} 项 · 原组成员 {source.source.members.length} 项；未处理项仍完整保留。</p>
        <Link href={`/review/investigations/${identity.task_id}/group-rules/${identity.source_rule_preparation_id}`}>查看组规则独立审核</Link>
      </section>
      <div className="group-fact-row">
        <section className="human-test-panel"><h2>当前官方原文</h2><p>当前页 {view.evidence_options.length} 段；分页只改变阅读位置，不表示证据已全部核验。</p>
          {view.evidence_options.map(e => <article key={`${e.block_id}:${e.member_id}`}><blockquote>{e.text}</blockquote><p><Link href={`/review/investigations/${identity.task_id}/materials/${encodeURIComponent(e.material_id)}`}>下载原件 · {e.material_id}</Link></p><details><summary>证据定位</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(e.locator, null, 2)}</pre></details></article>)}
          {!view.evidence_options.length ? <p>当前页没有可读取段落，不能据此判定没有限制。</p> : null}
          {view.next_cursor ? <button className="button button-secondary" disabled={busy} onClick={() => void read(view.next_cursor)}>读取下一页原文</button> : null}
        </section>
        <section className="human-test-panel"><h2>组条件与成员</h2>
          {facts.rows.map(row => <article key={row.source_index}><h3>{row.original_field}</h3><p>{row.original.value ?? "信息不足"} · {row.original_status}</p></article>)}
          <h3>完整成员清单</h3><ul>{source.source.members.map(m => <li key={m.entity_id}>{m.entity_id} · {m.state === "BOUND" ? "已有岗位绑定" : "尚未处理"}</li>)}</ul>
          <h3>本条组规则批准</h3><p>{view.approval.reason}</p><p>该批准针对单位组，尚不是岗位适用决定。</p>
          <h3>岗位未完成项</h3><p>{view.target_plan.plan.manifest.upstream_blockers.join("、") || "仍需独立核对完整适用范围"}</p>
        </section>
      </div>
    </> : null}
  </main>;
}

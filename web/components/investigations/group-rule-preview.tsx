"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { loadGroupRulePreviewAction } from "../../app/review/investigations/group-rule-actions";
import { groupRuleReasons, type GroupRuleResult } from "../../lib/group-rules";
import { groupFactRecordPath } from "../../lib/group-facts";
import { EvidenceCheckDetail } from "./evidence-check";
export default function GroupRulePreview({ taskId, prepId, initialResult }: { taskId: string; prepId: string; initialResult: GroupRuleResult }) {
  const [result, setResult] = useState<GroupRuleResult | null>(initialResult), [busy, setBusy] = useState(false);
  const active = useRef(false);
  async function reload() {
    if (active.current) return;
    active.current = true; setBusy(true); setResult(null);
    try { setResult(await loadGroupRulePreviewAction(taskId, prepId)); }
    catch { setResult({ ok: false, kind: "unavailable", error: "暂未取得当前规则预览，旧内容已隐藏。" }); }
    finally { active.current = false; setBusy(false); }
  }
  const data = result?.ok ? result.value.result : null;
  return <main id="main-content" className="page-shell human-test-shell investigation-shell">
    <nav className="breadcrumbs" aria-label="面包屑"><Link href={groupFactRecordPath(taskId, prepId)}>返回组字段审核</Link></nav>
    <h1>单位组规则预览</h1>
    <aside className="fixture-notice">本页只读。预览不代表规则获批，也不批准岗位继承或完整资格；整体资格仍为 UNCERTAIN。</aside>
    {result && !result.ok ? <section role="alert" className="human-test-panel"><h2>当前预览不可用</h2><p>{result.error}</p></section> : null}
    <button className="button button-secondary" disabled={busy} onClick={() => void reload()}>{busy ? "正在核对…" : "重新读取当前预览"}</button>
    {data ? <>
      <section className="human-test-panel"><h2>{data.target.label}</h2><p>组版本 {data.target.version} · {data.target.public_id}</p>
        {data.fact_review.fact_set ? <Link href={`/review/investigations/${encodeURIComponent(taskId)}/group-facts/${encodeURIComponent(prepId)}/rules/review`}>进入独立规则审核</Link> : null}
        <p>原组字段 {data.rows.length} 项 · 可预览规则 {data.rows.filter(row => row.proposed_rule_payload).length} 项 · 其他层级 {data.fact_review.result.excluded_rows.length} 项保留排除记录。</p>
        <p>{data.fact_review.fact_set ? `事实集已保存 · 版本 ${data.fact_review.fact_set.version}；规则仍需独立审核。` : "尚未保存正式事实集，当前只展示待处理条件。"}</p>
      </section>
      {!data.rows.length ? <p className="human-test-panel">原组没有字段，没有可预览规则。</p> : null}
      {data.rows.map((row, index) => {
        const source = data.fact_review.result.rows[index], payload = row.proposed_rule_payload;
        return <article className="human-test-panel group-fact-row" key={row.source_index} aria-label={`规则预览：${source.original_field}`}>
          <div><h2>{source.original_field}</h2><p>原始候选：{source.raw_value ?? "未披露"}</p><p>原始调查状态：{source.original_status}</p>
            {source.original.note ? <p>原备注：{source.original.note}</p> : null}
            {source.evidence.map((e, i) => <div key={i}><blockquote>{e.reference.quote}</blockquote><EvidenceCheckDetail evidence={e.reference} receipt={e.check_reference} />
              <a href={`/review/investigations/${encodeURIComponent(taskId)}/materials/${encodeURIComponent(e.reference.artifact_id)}`}>下载原件 · {e.reference.artifact_id}</a>
              <details><summary>查看原定位与证据块</summary><pre className="investigation-json">{JSON.stringify(e.reference.locator, null, 2)}</pre>{e.binding ? <blockquote>{e.binding.block_text}</blockquote> : <p>尚未完成机械核验，不计为 PASS。</p>}</details>
            </div>)}
          </div><div><h3>规则预览结果</h3><p role="status">{groupRuleReasons[row.reason_code]}</p>
            {payload ? <><p>{payload.reason_template}</p><p>规则值：{JSON.stringify(payload.value)}</p><details><summary>查看规则表达式</summary><pre className="investigation-json">{JSON.stringify(payload, null, 2)}</pre></details></> : <p>没有可执行规则预览；该条件仍保留在原始分母中。</p>}
          </div>
        </article>;
      })}
      <details className="human-test-panel"><summary>查看预览依据与完整分母</summary><pre className="investigation-json">{JSON.stringify({ source_row_count: data.fact_review.result.source_row_count, excluded_rows: data.fact_review.result.excluded_rows, result_hash: result?.ok ? result.value.result_hash : null, derivation_version: data.derivation_version }, null, 2)}</pre></details>
    </> : null}
  </main>;
}

"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { loadAnnouncementPreviewAction, loadAnnouncementRecordAction, saveAnnouncementSnapshotAction } from "../../app/review/investigations/announcement-snapshot-actions";
import { announcementPreviewPath, announcementRecordPath, announcementReasons, type AnnouncementCondition, type AnnouncementSnapshotData, type AnnouncementSnapshotResult } from "../../lib/announcement-snapshots";
import { applicabilityOutcomes } from "../../lib/rule-applicability";
import { formatDateTime } from "../../lib/public-opportunities";
import { currentSnapshotSource } from "../../lib/unit-snapshots";
import { materialPath, safeOfficialUrl } from "../../lib/investigation-evidence-links";
import UnitPlanView from "./unit-plan-view";

const groups = { INHERITED: "继承的公告条件", EXCLUDED: "明确排除的公告条件", UNRESOLVED: "仍待处理的公告条件" } as const;
function valueText(value: unknown): string {
  const values: Record<string, string> = { MASTER: "硕士", BACHELOR: "本科", DOCTORATE: "博士", ASSOCIATE: "专科", SECONDARY: "中等教育" };
  return typeof value === "string" ? values[value] ?? value : value === null ? "未确定" : JSON.stringify(value);
}
function ConditionView({ row, data }: { row: AnnouncementCondition; data: AnnouncementSnapshotData }) {
  const base = data.input.snapshot.base_v2, original = currentSnapshotSource(base, data.task)!.source_rows[row.condition.source_index];
  const app = row.applicability, approval = row.source_rule_approval, fact = row.source_fact;
  return <article className="human-test-panel announcement-condition">
    <h3>{original.original_field}</h3>
    <p>来源：公告 · {row.condition.source_entity_id} · 原字段序号 {row.condition.source_index + 1}</p>
    <p style={{ whiteSpace: "pre-wrap" }}>原始内容：{original.original.value ?? "未披露"}</p>
    {original.original.note ? <p className="risk-note">公告备注：{original.original.note}</p> : null}
    <p>{row.disposition === "INHERITED" ? "已按当前适用性决定继承此公告规则，仅形成范围记录。" : row.disposition === "EXCLUDED" ? "已明确排除此公告规则对本岗位的适用性，原条件和决定继续保留。" : "此公告条件仍待处理，未作为已继承或已排除条件。"}</p>
    {row.reasons.length ? <ul>{row.reasons.map(reason => <li key={reason}>{announcementReasons[reason] ?? `仍待复核（${reason}）`}</li>)}</ul> : null}
    {fact ? <>
      <p>公告审核事实：{valueText(fact.normalized_value)} · {fact.fact_state === "KNOWN" ? "已知" : "未知"}</p>
      <p className="investigation-hash">公告事实标识：{fact.verified_fact_id}；事实集：{fact.verified_fact_set_id}</p>
      <details><summary>查看公告事实与字段裁决</summary><pre className="investigation-json">{JSON.stringify(fact, null, 2)}</pre></details>
    </> : <p>尚无已保存的公告审核事实。</p>}
    {row.source_rule ? <>
      <p>已批准公告规则：{row.source_rule.field ?? "组合条件"} · {row.source_rule.operator} · {valueText(row.source_rule.value)}</p>
      <p className="investigation-hash">公告规则标识：{row.source_rule.rule_id}</p>
      <details><summary>查看原公告规则</summary><pre className="investigation-json">{JSON.stringify(row.source_rule, null, 2)}</pre></details>
    </> : <p>尚无可采用的已批准公告规则。</p>}
    {approval ? <details><summary>查看独立规则批准</summary>
      <p>批准人：{approval.approval.approver_identity} · {formatDateTime(approval.approval.decided_at)}</p>
      <p style={{ whiteSpace: "pre-wrap" }}>{approval.request.reason}</p>
      <p className="investigation-hash">规则决定：{approval.decision_id}；来源规则准备：{approval.rule_preparation_id}</p>
      <pre className="investigation-json">{JSON.stringify(approval, null, 2)}</pre>
    </details> : null}
    {app ? <section aria-label="当前适用性依据">
      <h4>对本岗位的适用性：{applicabilityOutcomes[app.request.outcome]}</h4>
      <p style={{ whiteSpace: "pre-wrap" }}>{app.request.reason}</p>
      <p>审核人：{app.reviewer_id} · {formatDateTime(app.created_at)}</p>
      <p className="investigation-hash">适用性决定：{app.decision_id} · 第 {app.sequence} 次</p>
      {app.evidence_snapshot.map((evidence, index) => { const url = safeOfficialUrl(evidence.source_url); return <div key={`${evidence.member_id}:${evidence.block_id}:${index}`}>
        <blockquote style={{ whiteSpace: "pre-wrap" }}>{evidence.quote}</blockquote>
        <p><a href={materialPath(data.task.task_id, evidence.material_id)}>下载适用性原件</a>{" · "}{url ? <a href={url} target="_blank" rel="noopener noreferrer">查看适用性官方原文</a> : <span>官方地址不可用</span>}</p>
        <details><summary>查看适用性原文位置与来源身份</summary><pre className="investigation-json">{JSON.stringify(evidence, null, 2)}</pre></details>
      </div>; })}
      <Link prefetch={false} href={`/review/investigations/${encodeURIComponent(data.task.task_id)}/unit-plans/${encodeURIComponent(base.plan_id)}/applicability/${encodeURIComponent(app.context.source_rule_preparation_id)}/${encodeURIComponent(app.context.source_rule_candidate_id)}`}>查看或追加适用性决定</Link>
      <details><summary>查看完整适用性记录</summary><pre className="investigation-json">{JSON.stringify(app, null, 2)}</pre></details>
    </section> : <p>尚无对本岗位的适用性决定。</p>}
    <details><summary>查看完整源条件身份</summary><pre className="investigation-json">{JSON.stringify(row.condition, null, 2)}</pre></details>
  </article>;
}

export default function AnnouncementSnapshotReview({ taskId, basePlanId, snapshotId, initialResult }: { taskId: string; basePlanId?: string; snapshotId?: string; initialResult: AnnouncementSnapshotResult }) {
  const [data, setData] = useState<AnnouncementSnapshotData | null>(initialResult.ok ? initialResult.value : null);
  const [baseId, setBaseId] = useState(basePlanId ?? (initialResult.ok ? initialResult.value.input.snapshot.base_v2.plan_id : null));
  const [recordId, setRecordId] = useState(snapshotId ?? (initialResult.ok ? initialResult.value.record?.snapshot_id : null));
  const [error, setError] = useState(initialResult.ok ? null : initialResult.error);
  const [retryHash, setRetryHash] = useState<string | null>(null);
  const [busy, setBusy] = useState(false), inFlight = useRef(false);
  const source = data ? currentSnapshotSource(data.input.snapshot.base_v2, data.task) : null;
  const targetName = data?.task.binding_entities?.find(entity => entity.id === source?.entity_id)?.name ?? source?.target.name;
  async function perform(saving: boolean) {
    if (inFlight.current) return;
    const hash = retryHash ?? data?.input.dependencies_hash;
    if (saving && (!baseId || !hash)) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      const result = saving ? await saveAnnouncementSnapshotAction({ task_id: taskId, base_plan_id: baseId! }, hash!)
        : recordId ? await loadAnnouncementRecordAction(taskId, recordId)
          : baseId ? await loadAnnouncementPreviewAction({ task_id: taskId, base_plan_id: baseId })
            : { ok: false, kind: "invalid", error: "请从当前基础快照重新进入。" } as const;
      if (result.ok) { setData(result.value); setBaseId(result.value.input.snapshot.base_v2.plan_id); setRecordId(result.value.record?.snapshot_id ?? null); setRetryHash(null); }
      else { setData(null); setError(result.error); setRetryHash(saving && result.kind === "unavailable" ? hash! : null); }
    } catch {
      setData(null); setError("暂未取得当前快照，旧内容已隐藏。请明确重试或重新读取。"); setRetryHash(saving ? hash! : null);
    } finally { inFlight.current = false; setBusy(false); }
  }
  return <main id="main-content" className="page-shell human-test-shell investigation-shell announcement-snapshot-shell">
    <nav className="breadcrumbs" aria-label="面包屑"><Link href={`/review/investigations/${encodeURIComponent(taskId)}`}>返回调查任务</Link>{baseId ? <Link href={`/review/investigations/${encodeURIComponent(taskId)}/unit-plans/${encodeURIComponent(baseId)}`} prefetch={false}>返回基础快照</Link> : null}</nav>
    <h1>公告继承范围快照</h1>
    {data ? <p>目标岗位：{targetName} · 岗位版本 {data.input.snapshot.base_v2.plan.target.unit_version}</p> : null}
    <aside className="fixture-notice">整体资格仍为 UNCERTAIN。本页仅整理公告规则对岗位的范围关系，尚不能用于个人资格判断，也不解除完整范围、例外和证据未核验事项。</aside>
    {error ? <section className="human-test-panel" role="alert"><h2>公告继承快照暂不可用</h2><p>{error}</p></section> : null}
    <div className="announcement-snapshot-actions">
      <button className="button button-secondary" disabled={busy} onClick={() => void perform(false)}>{busy ? "正在核对…" : recordId ? "重新核对已存快照" : "重新获取当前输入"}</button>
      {recordId && baseId ? <Link className="button button-secondary" href={announcementPreviewPath({ task_id: taskId, base_plan_id: baseId })} prefetch={false}>读取当前公告来源</Link> : null}
      {retryHash ? <button className="button button-primary" disabled={busy} onClick={() => void perform(true)}>重试保存原摘要</button> : null}
    </div>
    {data ? <>
      <section className="human-test-panel" aria-label="派生快照记录">
        <h2>{data.record ? "已保存的范围记录" : "当前输入预览"}</h2>
        <p>{data.record ? "保存只记录当时的来源关系；本次打开已重新核对全部当前依赖。" : "预览不会自动写入。确认当前来源与范围关系后，可明确保存这份派生快照。"}</p>
        {data.record ? <><p>保存于 {formatDateTime(data.record.created_at)} · 操作人 {data.record.reviewer_id}</p><Link href={announcementRecordPath(taskId, data.record.snapshot_id)} prefetch={false}>打开已保存快照</Link></>
          : <button className="button button-primary" disabled={busy} onClick={() => void perform(true)}>{busy ? "正在保存并核对…" : "保存当前派生快照"}</button>}
        <p>本页保留 {data.input.snapshot.announcement_conditions.length} 条公告源条件；基础快照中的岗位、单位组、备注和其他未处理事项继续完整展示。</p>
        <details><summary>依赖摘要与版本</summary><p className="investigation-hash">依赖摘要：{data.input.dependencies_hash}</p><p>{data.input.snapshot.contract_version}</p>
          {data.record ? <><p className="investigation-hash">派生快照标识：{data.record.snapshot_id}</p><p className="investigation-hash">快照摘要：{data.record.snapshot_hash}</p></> : null}
          <pre className="investigation-json">{JSON.stringify(data.input.dependencies, null, 2)}</pre>
        </details>
      </section>
      {(Object.entries(groups) as [AnnouncementCondition["disposition"], string][]).map(([kind, label]) => {
        const rows = data.input.snapshot.announcement_conditions.filter(row => row.disposition === kind);
        return <section key={kind} aria-labelledby={`announcement-${kind}`}><h2 id={`announcement-${kind}`}>{label} · {rows.length}</h2>
          {rows.length ? rows.map(row => <ConditionView key={row.condition.condition_id} row={row} data={data} />) : <p>当前没有此类公告条件。</p>}
        </section>;
      })}
      <section aria-labelledby="announcement-base"><h2 id="announcement-base">完整基础条件快照</h2>
        <p>以下保留基础快照的原始分母与处置语义；上方公告继承关系作为独立派生记录展示。</p>
        <UnitPlanView snapshot={data.input.snapshot.base_v2} task={data.task} embedded />
      </section>
    </> : null}
  </main>;
}

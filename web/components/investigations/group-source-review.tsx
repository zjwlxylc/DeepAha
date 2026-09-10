"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { loadGroupPreviewAction, loadGroupRecordAction, saveGroupSourceAction } from "../../app/review/investigations/group-source-actions";
import { groupPreviewPath, groupRecordPath, type GroupSourceData, type GroupSourceResult } from "../../lib/group-sources";
import { formatDateTime } from "../../lib/public-opportunities";
import { groupFactStartPath } from "../../lib/group-facts";

export default function GroupSourceReview({ taskId, entityId, recordId: initialRecordId, initialResult }: { taskId: string; entityId?: string; recordId?: string; initialResult: GroupSourceResult }) {
  const [data, setData] = useState<GroupSourceData | null>(initialResult.ok ? initialResult.value : null);
  const [sourceId, setSourceId] = useState(entityId ?? (initialResult.ok ? initialResult.value.preview.source.source_group.id : null));
  const [recordId, setRecordId] = useState(initialRecordId ?? (initialResult.ok ? initialResult.value.preview.registration?.group_binding_id : null));
  const [error, setError] = useState(initialResult.ok ? null : initialResult.error);
  const [retryHash, setRetryHash] = useState<string | null>(null);
  const [busy, setBusy] = useState(false), inFlight = useRef(false);
  async function perform(saving: boolean) {
    if (inFlight.current) return;
    const hash = retryHash ?? data?.preview.source_hash;
    if (saving && (!sourceId || !hash)) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      const result = saving ? await saveGroupSourceAction({ task_id: taskId, entity_id: sourceId! }, hash!)
        : recordId ? await loadGroupRecordAction(taskId, recordId)
          : sourceId ? await loadGroupPreviewAction({ task_id: taskId, entity_id: sourceId })
            : { ok: false, kind: "invalid", error: "请返回调查任务读取当前组来源。" } as const;
      if (result.ok) { setData(result.value); setSourceId(result.value.preview.source.source_group.id); setRecordId(result.value.preview.registration?.group_binding_id ?? null); setRetryHash(null); }
      else { setData(null); setError(result.error); setRetryHash(saving && result.kind === "unavailable" ? hash! : null); }
    } catch {
      setData(null); setError("暂未取得当前来源，旧内容已隐藏。请明确重试或重新读取。"); setRetryHash(saving ? hash! : null);
    } finally { inFlight.current = false; setBusy(false); }
  }
  const source = data?.preview.source, record = data?.preview.registration;
  return <main id="main-content" className="page-shell human-test-shell investigation-shell group-source-shell">
    <nav className="breadcrumbs" aria-label="面包屑"><Link href={`/review/investigations/${encodeURIComponent(taskId)}`}>返回调查任务</Link></nav>
    <h1>单位组来源登记</h1>
    <aside className="fixture-notice">身份已关联不代表事实、规则或资格已批准。组条件和证据仍需单独核验，整体资格保持 UNCERTAIN。</aside>
    {error ? <section className="human-test-panel" role="alert"><h2>组来源暂不可用</h2><p>{error}</p></section> : null}
    <div className="announcement-snapshot-actions">
      <button className="button button-secondary" disabled={busy} onClick={() => void perform(false)}>{busy ? "正在核对…" : recordId ? "重新核对已登记来源" : "重新获取当前输入"}</button>
      {recordId && sourceId ? <Link className="button button-secondary" prefetch={false} href={groupPreviewPath({ task_id: taskId, entity_id: sourceId })}>读取当前组来源</Link> : null}
      {retryHash ? <button className="button button-primary" disabled={busy} onClick={() => void perform(true)}>重试登记原摘要</button> : null}
    </div>
    {data && source ? <>
      <section className="human-test-panel" aria-label="组来源记录">
        <h2>{record ? "已登记的组来源" : "当前组来源预览"}</h2>
        <p>来源组：{source.source_group.name ?? source.source_group.id}</p>
        {record ? <Link prefetch={false} href={groupFactStartPath(taskId, record.group_binding_id)}>进入组字段审核</Link> : null}
        <p>所属机会：{data.task.entity_binding!.opportunity_title} · 机会版本 {source.opportunity_version}</p>
        <p>{record ? "本次打开已重新核对当前来源与身份。保存仅记录组与成员的来源关系。" : "预览不会自动登记。下列成员按原组完整保留，未处理成员也会保留在记录中。"}</p>
        {record ? <><dl className="compact-facts"><div><dt>稳定组标识</dt><dd>{record.group_identity.public_id}</dd></div><div><dt>组版本</dt><dd>{record.group_identity.version}</dd></div><div><dt>登记时间</dt><dd>{formatDateTime(record.created_at)}</dd></div></dl><Link prefetch={false} href={groupRecordPath(taskId, record.group_binding_id)}>打开已登记来源</Link></>
          : <>{data.preview.existing_group_id ? <p>将沿用已有组身份，按当前来源追加版本。</p> : null}<button className="button button-primary" disabled={busy} onClick={() => void perform(true)}>{busy ? "正在登记并核对…" : "登记当前组来源"}</button></>}
        <details><summary>查看来源与版本依据</summary><p className="investigation-hash">来源摘要：{data.preview.source_hash}</p><p>{source.contract_version}</p>
          {record ? <><p className="investigation-hash">登记标识：{record.group_binding_id}</p><p className="investigation-hash">操作人：{record.reviewer_id}</p></> : null}
          <pre className="investigation-json">{JSON.stringify(source, null, 2)}</pre>
        </details>
      </section>
      <section aria-labelledby="group-members-title"><h2 id="group-members-title">完整组成员 · {source.members.length}</h2>
        <p>{source.membership_status === "NO_MEMBERS" ? "原组没有成员，不能据此推定存在可申请岗位。" : source.membership_status === "ALL_MEMBERS_BOUND" ? "全部成员已关联身份；组条件和资格仍未完成审核。" : "仍有成员未处理，来源登记会保留这些缺口。"}</p>
        <div className="group-member-grid">{source.members.map((member, index) => {
          const original = source.source_group.positions[index];
          return <article className="human-test-panel" key={member.entity_id}><h3>{original.name ?? member.entity_id}</h3>
            <p>{member.state === "BOUND" ? "身份已关联 · BOUND" : "未处理 · UNPROCESSED"}</p>
            <p>原编号：{original.code ?? "未披露"}</p><p className="investigation-hash">原成员标识：{member.entity_id}</p>
            {member.position_binding ? <details><summary>查看岗位身份与版本</summary><pre className="investigation-json">{JSON.stringify(member.position_binding, null, 2)}</pre></details> : <p>尚无当前岗位身份，不会被当作已关联成员。</p>}
          </article>;
        })}</div>
      </section>
      <details className="human-test-panel"><summary>查看完整原组内容与备注</summary><pre className="investigation-json">{JSON.stringify(source.source_group, null, 2)}</pre></details>
    </> : null}
  </main>;
}

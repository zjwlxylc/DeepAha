import Link from "next/link";
import { randomUUID } from "node:crypto";
import { getInvestigationWorkbench } from "../../../../../lib/investigations";
import { LocalHumanTestApiError } from "../../../../../lib/local-human-test";
import { reviewHref, selectedPositions } from "../../../../../lib/guided-review";
import GuidedSelection from "../../../../../components/investigations/guided-selection";
import GuidedIdentity from "../../../../../components/investigations/guided-identity";
import GuidedFact from "../../../../../components/investigations/guided-fact";
import GuidedRule from "../../../../../components/investigations/guided-rule";
import GuidedPrepare from "../../../../../components/investigations/guided-prepare";

export default async function GuidedReviewPage({ params, searchParams }: { params: Promise<{ taskId: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { taskId } = await params, input = await searchParams;
  const queue = typeof input.queue === "string" ? input.queue : "";
  let base;
  try { base = await getInvestigationWorkbench(taskId, new URLSearchParams()); }
  catch (error) {
    if (error instanceof LocalHumanTestApiError) return <main className="page-shell guided-review" id="main-content"><h1>暂时无法读取这次核对</h1><p>{error.status === 401 ? "登录已失效，请用本地测试启动入口重新打开已登录的浏览器。" : "服务或材料暂时不可用，你之前保存的记录不会因此丢失。"}</p><Link href="/review/investigations">返回任务列表</Link></main>;
    throw error;
  }
  const ids = selectedPositions(base, typeof input.position === "string" ? [input.position] : input.position ?? []).map(e => e.id);
  const positions = selectedPositions(base, ids);
  const stage = input.stage === "rules" || input.stage === "summary" ? input.stage : "facts";
  const entity = typeof input.entity_id === "string" && ids.includes(input.entity_id) ? input.entity_id : ids[0];
  const offset = typeof input.offset === "string" && /^\d{1,5}$/.test(input.offset) ? Number(input.offset) : 0;
  const bothBound = positions.length === 2 && positions.every(e => base.entity_binding?.positions.some(p => p.entity_id === e.id));
  const ready = base.status === "APPROVED" && base.document_preparation?.status === "PREPARED"
    && (!base.entity_binding || base.entity_binding.bundle_status === "FROZEN");
  let task = base;
  if (bothBound && stage !== "summary") task = await getInvestigationWorkbench(taskId, new URLSearchParams({ entity_id: entity, offset: String(offset) }));
  const prep = task.fact_review?.current, rules = task.rule_review?.current[0];
  const superseded = prep?.promotions[entity] && (prep.promotions[entity].status !== "ACTIVE"
    || prep.promotions[entity].fact_set_id !== prep.active_fact_sets[entity]?.fact_set_id);
  const ruleCurrent = rules && prep && rules.binding_id === prep.binding_id && rules.check_id === prep.check_id
    && rules.fact_preparation_id === prep.preparation_id && rules.fact_preparation_hash === prep.result_hash
    && rules.fact_set_id === prep.active_fact_sets[entity]?.fact_set_id;
  const fieldTotal = prep?.slice?.total ?? 0, total = stage === "rules" ? rules?.slice?.total ?? 0 : fieldTotal;
  const current = positions.find(p => p.id === entity);
  const units = (base.opportunities?.units ?? []) as { name: string; positions: { id: string }[] }[];
  const unitName = (id: string) => units.find(u => u.positions.some(p => p.id === id))?.name ?? "所属单位待核对";
  const href = (target: string, nextStage = "facts", nextOffset = 0) => reviewHref(taskId, ids, target, nextStage, nextOffset, queue);
  const next = href(entity, stage, offset + 1);
  const nextPosition = ids[ids.indexOf(entity) + 1];
  const summary = reviewHref(taskId, ids, entity, "summary", 0, queue);
  const summaries = bothBound && stage === "summary" ? await Promise.all(ids.map(id => getInvestigationWorkbench(taskId, new URLSearchParams({ entity_id: id })))) : [];
  return <main className="page-shell guided-review" id="main-content">
    <nav className="guided-top" aria-label="审核导航"><Link href={`/review/investigations?${new URLSearchParams(queue)}`}>← 返回任务列表</Link><Link href={`/review/investigations/${taskId}`}>材料与管理记录</Link></nav>
    <p className="guided-notice-title">{String(base.opportunities?.opportunity_name ?? "岗位核对")}</p>
    {!ready ? <section className="guided-card"><h1>先准备好这份公告</h1><p>目前材料尚未批准，或附件文字没有准备好。请先处理材料；这里不会重新发起调查。</p><Link className="button button-primary" href={`/review/investigations/${taskId}#investigation-documents-title`}>查看材料准备情况</Link></section>
      : ids.length !== 2 ? <GuidedSelection task={base} queue={queue} />
        : !bothBound ? <GuidedIdentity key={`${base.entity_binding?.binding_id ?? base.delivery_hash}:${ids.join()}`} task={base} ids={ids} requestKey={randomUUID()} />
          : stage === "summary" ? <section className="guided-card"><h1>这次核对记录</h1><p>下面显示当前保存的状态。待处理可以保留，不需要为了结束本轮而批准。</p>
            {summaries.map((s, i) => <article className="guided-summary-row" key={s.task_id + ids[i]}><h2>{positions[i].name} · {positions[i].code}</h2><p>{unitName(ids[i])} · 岗位已确认</p><p>{s.fact_review?.current ? `原始内容 ${s.fact_review.current.slice?.total ?? 0} 条 · 仍需处理 ${s.fact_review.current.slice?.attention_total ?? "待统计"} 条` : "尚未开始内容核对"}</p>
              <p>{s.fact_review?.current?.promotions[ids[i]] ? "内容已归入岗位记录" : "内容尚未归入岗位记录，待处理不等于批准"}</p>
              <p>{s.rule_review?.current[0] ? `判断条件 ${s.rule_review.current[0].slice?.total ?? 0} 条；仍需处理 ${s.rule_review.current[0].slice?.unresolved_total ?? "待统计"} 条` : "判断条件尚未准备或仍被待处理内容阻塞"}</p>
              <Link href={href(ids[i])}>继续核对这个岗位</Link></article>)}
            <aside className="guided-limits">公告共同条件、单位共同条件以及完整资格范围仍需核对。本页只报告已保存记录，不表示资格通过或允许发布。</aside>
            <Link className="button button-secondary" href={`/review/investigations/${taskId}/workbench?step=identity&view=advanced`}>查看共同条件与完整记录</Link>
          </section> : <>
            <header className="guided-current"><p className="eyebrow">第 3 步，共 3 步 · 逐条核对</p><h1>{current?.name}</h1><p>{unitName(entity)}</p><nav aria-label="这次选择的两个岗位">{positions.map(p => <Link key={p.id} href={href(p.id)} aria-current={p.id === entity ? "page" : undefined}>{p.name}{p.code ? ` · ${p.code}` : ""}</Link>)}</nav><p>{stage === "rules" ? "核对判断条件" : "核对原文内容"}{total && offset < total ? ` · 第 ${offset + 1} / ${total} 条` : ""}</p></header>
            {!prep || prep.binding_id !== task.entity_binding?.binding_id || prep.check_id !== task.evidence_check?.check_id ? task.evidence_check ? <GuidedPrepare task={task} kind="prepare" requestKey={randomUUID()} /> : <section className="guided-card"><h2>还缺少原文核验结果</h2><Link href={`/review/investigations/${taskId}#investigation-documents-title`}>查看材料核验情况</Link></section>
              : superseded ? <section className="guided-card"><h2>这个岗位的记录已有更新</h2><p>当前回答对应旧版本，暂不能继续生成判断条件。请查看最新记录，确认需要核对的版本。</p><Link href={`/review/investigations/${taskId}/workbench?view=advanced&step=facts&entity_id=${entity}`}>查看该岗位的最新记录</Link></section>
                : stage === "facts" && offset < total ? <GuidedFact key={`${prep.preparation_id}:${prep.rows[0]?.candidate_id}:${prep.rows[0]?.candidate_id ? prep.decisions[prep.rows[0].candidate_id]?.decision_id : ""}`} task={task} requestKey={randomUUID()} next={next} />
                : stage === "facts" ? <>
                  {prep.promotions[entity] ? <section className="guided-card"><h2>当前岗位内容已保存</h2><Link className="button button-primary" href={href(entity, "rules")}>继续核对判断条件</Link></section>
                    : prep.slice?.can_promote ? <GuidedPrepare task={task} kind="promote" requestKey={randomUUID()} /> : <section className="guided-card"><h2>这个岗位还有待处理内容</h2><p>仍需处理 {prep.slice?.attention_total ?? "待统计"} 条。无法判断的回答已保留，可以先核对另一个岗位。</p>{prep.slice?.next_attention_offset != null ? <Link href={href(entity, "facts", prep.slice.next_attention_offset)}>返回待处理内容</Link> : null}</section>}
                  <Link className="button button-secondary" href={nextPosition ? href(nextPosition) : summary}>{nextPosition ? "继续第二个岗位" : "查看本次记录"}</Link>
                </> : !prep.promotions[entity] ? <section className="guided-card"><h2>请先核对原文内容</h2><Link className="button button-primary" href={href(entity)}>返回内容核对</Link></section>
                  : !rules || !ruleCurrent ? <GuidedPrepare task={task} kind="rules" requestKey={randomUUID()} />
                    : offset < total ? <GuidedRule key={`${rules.rule_preparation_id}:${rules.rows[0]?.rule_candidate_id}:${rules.rows[0]?.rule_candidate_id ? rules.decisions[rules.rows[0].rule_candidate_id]?.decision_id : ""}`} task={task} requestKey={randomUUID()} next={next} />
                      : <section className="guided-card"><h2>已到这个岗位的最后一条</h2><p>这只表示已浏览到末尾。未保存、未知及待裁决内容仍在记录中，不算批准。</p><Link className="button button-primary" href={nextPosition ? href(nextPosition) : summary}>{nextPosition ? "继续第二个岗位" : "查看本次记录"}</Link></section>}
            <nav className="guided-bottom" aria-label="当前核对进度">{offset > 0 ? <Link href={href(entity, stage, offset - 1)}>← 上一条</Link> : <span>回答会在点击保存后写入</span>}<Link href={summary}>查看已保存与待处理</Link></nav>
          </>}
    <p className="guided-footnote">未提交回答仅保留在当前窗口；刷新或关闭前请先保存。已保存记录可重新打开查看。</p>
  </main>;
}

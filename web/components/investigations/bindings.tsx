import { randomUUID } from "node:crypto";
import type { InvestigationBindingTarget, InvestigationTask } from "../../lib/investigations";
import InvestigationIdentityForm from "./identity-form";
import InvestigationBindingForm from "./binding-form";

export default function InvestigationBindings({ task, targets }: { task: InvestigationTask; targets: InvestigationBindingTarget[] }) {
  const binding = task.entity_binding;
  const ready = task.status === "APPROVED" && task.document_preparation?.status === "PREPARED";
  return <section className="human-test-panel" aria-labelledby="investigation-binding-title">
    <h2 id="investigation-binding-title">机会与岗位归属</h2>
    <p>归属确认只说明这批材料对应哪个机会和岗位。字段内容仍是候选，需另行审核。</p>
    {binding ? <>
      <p>当前关联：{binding.opportunity_title} · 机会版本 {binding.opportunity_version} · 归属修订 {binding.sequence}</p>
      <p>已关联 {binding.positions.length} 个岗位，仍有 {binding.unmapped_position_ids.length} 个岗位待关联。</p>
      <p>核对依据：{binding.reason}</p>
      {binding.bundle_status !== "FROZEN" ? <p className="risk-note">此来源包已失效，需要重新核对归属和材料。</p> : null}
      <details><summary>查看来源与归属记录</summary><dl className="compact-facts">
        <div><dt>来源方式</dt><dd>Direct WMA；网址由调查服务声明，已保留回收原件。</dd></div>
        <div><dt>机会公开标识</dt><dd>{binding.opportunity_public_id}</dd></div>
        <div><dt>来源包摘要</dt><dd>{binding.canonical_bundle_hash}</dd></div>
        <div><dt>关联记录</dt><dd>{binding.binding_id}</dd></div>
      </dl></details>
      {(task.binding_history?.length ?? 0) > 1 ? <details><summary>查看历次归属方案</summary>
        <ol>{task.binding_history?.map(item => <li key={item.binding_id}>
          修订 {item.sequence}：{item.opportunity_title} · 机会版本 {item.opportunity_version}；
          已关联 {item.positions.length} 个岗位，待关联 {item.unmapped_position_ids.length} 个。依据：{item.reason}
        </li>)}</ol>
      </details> : null}
    </> : <p>尚未确认归属。</p>}
    {ready && targets.length ? <InvestigationBindingForm key={binding?.binding_id ?? task.delivery_hash} task={task} targets={targets} requestKey={randomUUID()} />
      : ready ? <p>目前没有可选择的机会版本。请核对原件，首次登记内部机会身份。</p>
        : <p>请先完成内部材料审核及全部文档证据准备。</p>}
    {ready ? <InvestigationIdentityForm key={`identity:${binding?.binding_id ?? task.delivery_hash}`} task={task} requestKey={randomUUID()} /> : null}
  </section>;
}

import type { InvestigationTask } from "../../lib/investigations";
import PrepareDocumentsForm from "./prepare-documents-form";

const outcomes: Record<string, string> = {
  NOT_PREPARED: "尚未准备", SUCCEEDED: "文档证据已准备，语义待核对",
  NEEDS_REVIEW: "解析结果需复核", FAILED: "解析失败", UNSUPPORTED: "格式尚不支持，保留原件待处理",
};

export default function InvestigationDocuments({ task }: { task: InvestigationTask }) {
  if (!task.delivery_hash) return null;
  const preparation = task.document_preparation;
  const canPrepare = ["PENDING_REVIEW", "APPROVED"].includes(task.status);
  return <section className="human-test-panel" aria-labelledby="investigation-documents-title">
    <h2 id="investigation-documents-title">文档证据准备</h2>
    <p>只解析已回收的原件，供后续事实核对使用。此步骤需要运营权限；不会调用调查服务或批准事实。</p>
    {preparation ? <>
      <p>{preparation.prepared_count} / {preparation.material_count} 份材料已完成文档证据准备。</p>
      {preparation.status === "NEEDS_ATTENTION" ? <p className="risk-note">仍有未准备、需复核或不支持的材料，请逐项处理。</p> : null}
      <div className="candidate-list">{preparation.materials.map((material) => <article className="candidate-card" key={material.material_id}>
        <h3>{material.material_id}</h3>
        <p>{outcomes[material.outcome] ?? "状态待核对"}</p>
        <p>证据块：{material.block_count}；证据引用：{material.evidence_ref_count}</p>
        {material.document_parse_key ? <details><summary>查看解析版本</summary><p>{material.parser_name} · {material.parser_version}</p><p>{material.parse_contract_version}</p><p className="investigation-hash">{material.document_parse_key}</p></details> : null}
        {material.error_code ? <details><summary>待处理原因标识</summary><code>{material.error_code}</code></details> : null}
      </article>)}</div>
    </> : <p>尚未准备文档证据。</p>}
    {canPrepare ? <PrepareDocumentsForm taskId={task.task_id} deliveryHash={task.delivery_hash} requestKey={randomUUID()} key={task.delivery_hash} /> : null}
  </section>;
}
import { randomUUID } from "node:crypto";

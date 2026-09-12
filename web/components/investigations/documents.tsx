import type { InvestigationTask } from "../../lib/investigations";
import PrepareDocumentsForm from "./prepare-documents-form";
import ExcludeDocumentForm from "./exclude-document-form";
import { materialName } from "../../lib/investigation-evidence-links";

const outcomes: Record<string, string> = {
  NOT_PREPARED: "尚未准备", SUCCEEDED: "文档证据已准备，语义待核对",
  NEEDS_REVIEW: "解析结果需复核", FAILED: "解析失败", UNSUPPORTED: "格式尚不支持，保留原件待处理",
};

export default function InvestigationDocuments({ task }: { task: InvestigationTask }) {
  if (!task.delivery_hash) return null;
  const deliveryHash = task.delivery_hash;
  const preparation = task.document_preparation;
  const canPrepare = ["PENDING_REVIEW", "APPROVED"].includes(task.status);
  const materialCount = preparation?.material_count ?? 0;
  const excludedCount = preparation?.excluded_count ?? 0;
  const ratioWarning = excludedCount > 0 && materialCount > 0 && excludedCount / materialCount > 1 / 3;
  return <section className="human-test-panel" aria-labelledby="investigation-documents-title">
    <h2 id="investigation-documents-title">文档证据准备</h2>
    <p>把已保存的附件整理成可核对的文字和表格。点击下方“准备文档证据”即可；这一步不会重新调查，也不会替你确认内容正确。</p>
    {preparation ? <>
      {excludedCount > 0
        ? <p>{`已准备 ${preparation.prepared_count}/${materialCount} 份，其中 ${excludedCount} 份为无文本证据块的排除材料`}</p>
        : <p>{preparation.prepared_count} / {preparation.material_count} 份材料已完成文档证据准备。</p>}
      {preparation.status === "NEEDS_ATTENTION" ? <p className="risk-note">仍有未准备、需复核或不支持的材料，请逐项处理。</p> : null}
      {excludedCount > 0 ? <p className="risk-note">存在已排除材料：其字段不得作为块级依据，仅保留原件整文件引用。</p> : null}
      {ratioWarning ? <p className="risk-note">已排除材料占比超过三分之一，请确认范围是否仍然合理。</p> : null}
      <div className="candidate-list">{preparation.materials.map((material) => <article className="candidate-card" key={material.material_id}>
        <h3>{materialName(task.materials.find(item => item.artifact_id === material.material_id) ?? { artifact_id: material.material_id })}</h3>
        <p>{outcomes[material.outcome] ?? "状态待核对"}</p>
        {material.excluded ? <>
          <p className="risk-note">无文本证据块</p><p>这份附件仍可下载，但系统不能从中引用文字；相关条件需要另外核对。</p>
          <p>排除理由：{material.exclusion?.reason ?? "未记录"}</p>
          <p>操作人：{material.exclusion?.excluded_by ?? "未记录"}；时间：{material.exclusion?.excluded_at ?? "未记录"}</p>
        </> : null}
        <p>可核对的段落或表格：{material.block_count} 处；已关联引用：{material.evidence_ref_count} 处</p>
        {material.document_parse_key ? <details><summary>查看解析版本</summary><p>{material.parser_name} · {material.parser_version}</p><p>{material.parse_contract_version}</p><p className="investigation-hash">{material.document_parse_key}</p></details> : null}
        {material.error_code ? <details><summary>待处理原因标识</summary><code>{material.error_code}</code></details> : null}
        {/* Exclusion and revocation both change state, and the backend rejects
            them outside the reviewable states — so they follow the same gate as
            document preparation instead of offering a control that always fails. */}
        {canPrepare
          ? material.excluded
            ? <ExcludeDocumentForm mode="revoke" taskId={task.task_id} deliveryHash={deliveryHash} materialId={material.material_id} requestKey={randomUUID()} />
            : material.outcome === "UNSUPPORTED"
              ? <ExcludeDocumentForm mode="exclude" taskId={task.task_id} deliveryHash={deliveryHash} materialId={material.material_id} requestKey={randomUUID()} />
              : null
          : null}
      </article>)}</div>
    </> : <p>尚未准备文档证据。</p>}
    {canPrepare ? <PrepareDocumentsForm taskId={task.task_id} deliveryHash={deliveryHash} requestKey={randomUUID()} key={deliveryHash} /> : null}
  </section>;
}
import { randomUUID } from "node:crypto";

import type { InvestigationTask } from "../../lib/investigations";
import { EvidenceCheckDetail, EvidenceCheckSummary } from "./evidence-check";

const labels: Record<string, string> = {
  opportunity_name: "机会名称", publish_unit: "发布单位", opportunity_type: "机会类别",
  publish_date: "发布日期", registration_start: "报名开始", registration_deadline: "报名截止",
  work_location: "工作地点", application_method: "申请方式", official_contact: "官方联系方式",
  education: "学历要求", education_level: "学历要求", major: "专业要求", major_name: "专业要求",
  age: "年龄要求", eligibility: "资格条件", deadline: "截止时间", headcount: "人数",
  sheet: "工作表", row: "行", column: "列", cell: "单元格", page: "页码", url: "网页",
  selector: "页面位置", paragraph: "段落", start: "起点", end: "终点",
};
const factStatuses: Record<string, string> = { CONFIRMED: "候选认为有依据", CONFLICT: "证据冲突", INSUFFICIENT: "证据不足", UNKNOWN: "未知" };
const fileTypes: Record<string, string> = {
  "application/pdf": "PDF 文档",
  "text/html": "网页原件",
  "text/plain": "文本原件",
  "application/vnd.ms-excel": "Excel 工作簿",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel 工作簿",
};

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record) : [];
}
function readable(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未提供";
  if (Array.isArray(value)) return value.map(readable).join("、");
  if (typeof value === "object") return Object.entries(record(value)).map(([key, item]) => `${labels[key] ?? key}：${readable(item)}`).join("；");
  return String(value);
}
export function safeOfficialUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : undefined;
  } catch { return undefined; }
}
export function materialPath(taskId: string, artifactId: string): string {
  return `/review/investigations/${encodeURIComponent(taskId)}/materials/${encodeURIComponent(artifactId)}`;
}

export default function InvestigationEvidence({ task }: { task: InvestigationTask }) {
  const opportunity = task.opportunities ?? {};
  const units = records(opportunity.units);
  const entityNames = new Map<string, string>();
  for (const unit of units) {
    entityNames.set(String(unit.id), readable(unit.name));
    for (const position of records(unit.positions)) entityNames.set(String(position.id), `${readable(unit.name)} / ${readable(position.name)}`);
  }
  const factGroups = new Map<string, InvestigationTask["facts"]>();
  for (const fact of task.facts) factGroups.set(fact.entity_id, [...(factGroups.get(fact.entity_id) ?? []), fact]);
  const materialIds = new Set(task.materials.map((item) => item.artifact_id));
  return (
    <>
      <section className="human-test-panel" aria-labelledby="candidate-overview-title">
        <h2 id="candidate-overview-title">主机会与子项</h2>
        {task.opportunities ? <>
          <dl className="compact-facts">{Object.keys(labels).filter((key) => key in opportunity && (opportunity[key] === null || typeof opportunity[key] !== "object")).map((key) => <div key={key}><dt>{labels[key]}</dt><dd>{readable(opportunity[key])}</dd></div>)}</dl>
          {units.length ? <ul className="investigation-hierarchy">{units.map((unit, index) => <li key={String(unit.id ?? index)}><strong>{readable(unit.name)}</strong><small> · 标识 {readable(unit.id)}</small><ul>{records(unit.positions).map((position, positionIndex) => <li key={String(position.id ?? positionIndex)}>{readable(position.name)}{position.code ? ` · 编号 ${readable(position.code)}` : ""}<small> · 标识 {readable(position.id)}</small></li>)}</ul></li>)}</ul> : <p>尚未提供单位或岗位子项。</p>}
        </> : <p>尚未收到机会候选。</p>}
      </section>
      <section className="human-test-panel" aria-labelledby="investigation-facts-title">
        <h2 id="investigation-facts-title">字段、官方引文与定位</h2>
        <p className="risk-note" role="note">字节与引文定位核验不能证明完整语义。请人工检查适用实体、共同条件、例外和遗漏。</p>
        <EvidenceCheckSummary check={task.evidence_check} history={task.evidence_check_history} />
        {Array.from(factGroups, ([entityId, facts]) => <section className="investigation-entity" key={entityId}>
          <h3>{entityNames.get(entityId) ?? `公告或其他实体 · ${entityId}`}</h3>
          <div className="candidate-list">{facts.map((fact, index) => <article className="candidate-card" key={`${fact.field}-${index}`}>
            <div className="candidate-grid"><div><h4>{labels[fact.field] ?? fact.field}</h4><p>{fact.value ?? "未知 / 未提供"}</p><span className="status-badge">{factStatuses[fact.status] ?? `待核对 · ${fact.status}`}</span>
              {fact.note ? <div className="risk-note"><strong>调查备注（待人工核对）</strong><p>{fact.note}</p></div> : null}
            </div>
              <div>{fact.evidence.length ? fact.evidence.map((evidence, evidenceIndex) => <blockquote className="official-evidence-block" key={`${evidence.artifact_id}-${evidenceIndex}`}>
                <p>{evidence.quote || "未提供引文"}</p>
                <footer><p>{readable(evidence.locator)}</p><EvidenceCheckDetail evidence={evidence} receipt={task.evidence_check?.references.find((item) => item.fact_index === task.facts.indexOf(fact) && item.reference_index === evidenceIndex)} />
                  {materialIds.has(evidence.artifact_id) ? <a href={materialPath(task.task_id, evidence.artifact_id)}>下载原件 · {evidence.artifact_id}</a> : <p className="form-alert">关联原件尚不可下载</p>}
                </footer>
              </blockquote>) : <p className="form-alert">缺少关联证据，保持未知并补充核对。</p>}</div>
            </div>
          </article>)}</div>
        </section>)}
        {!task.facts.length ? <p>尚无可展示的字段证据。</p> : null}
      </section>
      <section className="human-test-panel" aria-labelledby="investigation-materials-title">
        <h2 id="investigation-materials-title">已保存的官方原件</h2>
        {task.materials.length ? <ul className="human-test-run-list">{task.materials.map((material) => <li key={material.artifact_id}>
          <strong>{material.artifact_id}</strong><div><a className="button button-secondary" href={materialPath(task.task_id, material.artifact_id)}>下载原件 · {material.artifact_id}</a>{safeOfficialUrl(material.url) ? <a href={safeOfficialUrl(material.url)} target="_blank" rel="noopener noreferrer">查看官方地址</a> : <span>官方地址不可用</span>}</div>
          <small>{fileTypes[material.media_type] ?? "官方原件"} · {material.size_bytes.toLocaleString("zh-CN")} 字节</small>
          <details><summary>文件完整性标识</summary><code className="investigation-hash">SHA-256：{material.sha256}</code></details>
        </li>)}</ul> : <p>尚无已保存的原件。任务登记或远端结束均不代表文件已交付。</p>}
      </section>
    </>
  );
}

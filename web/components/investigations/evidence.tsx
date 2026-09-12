"use client";

import type { InvestigationTask } from "../../lib/investigations";
import { EvidenceCheckDetail, EvidenceCheckSummary } from "./evidence-check";
import ReviewBrowser from "./review-browser";
import { materialName, materialPath, safeOfficialUrl } from "../../lib/investigation-evidence-links";

const labels: Record<string, string> = {
  opportunity_name: "机会名称", publish_unit: "发布单位", opportunity_type: "机会类别",
  publish_date: "发布日期", registration_start: "报名开始", registration_deadline: "报名截止",
  work_location: "工作地点", application_method: "申请方式", official_contact: "官方联系方式",
  education: "学历要求", education_level: "学历要求", major: "专业要求", major_name: "专业要求",
  age: "年龄要求", eligibility: "资格条件", deadline: "截止时间", headcount: "人数",
  sheet: "工作表", row: "行", column: "列", cell: "单元格", page: "页码", url: "网页",
  selector: "页面位置", paragraph: "段落", start: "起点", end: "终点",
};
const factStatuses: Record<string, string> = { CONFIRMED: "系统找到依据，待你确认", CONFLICT: "原文存在冲突", INSUFFICIENT: "依据还不够", UNKNOWN: "暂时无法判断" };
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
export default function InvestigationEvidence({ task }: { task: InvestigationTask }) {
  const opportunity = task.opportunities ?? {};
  const units = records(opportunity.units);
  const entityNames = new Map<string, string>();
  for (const unit of units) {
    entityNames.set(String(unit.id), readable(unit.name));
    for (const position of records(unit.positions)) entityNames.set(String(position.id), `${readable(unit.name)} / ${readable(position.name)}`);
  }
  const materialIds = new Set(task.materials.map((item) => item.artifact_id));
  return (
    <>
      <section className="human-test-panel" aria-labelledby="candidate-overview-title">
        <h2 id="candidate-overview-title">这份公告涉及哪些单位和岗位</h2>
        {task.opportunities ? <>
          <dl className="compact-facts">{Object.keys(labels).filter((key) => key in opportunity && (opportunity[key] === null || typeof opportunity[key] !== "object")).map((key) => <div key={key}><dt>{labels[key]}</dt><dd>{readable(opportunity[key])}</dd></div>)}</dl>
          {units.length ? <div className="review-hierarchy-scroll"><ul className="investigation-hierarchy">{units.map((unit, index) => <li key={String(unit.id ?? index)}><strong>{readable(unit.name)}</strong><details><summary>查看 {records(unit.positions).length} 个岗位</summary><ul>{records(unit.positions).map((position, positionIndex) => <li key={String(position.id ?? positionIndex)}>{readable(position.name)}{position.code ? ` · 编号 ${readable(position.code)}` : ""}</li>)}</ul></details></li>)}</ul></div> : <p>尚未提供单位或岗位子项。</p>}
        </> : <p>尚未收到机会候选。</p>}
      </section>
      <section className="human-test-panel" aria-labelledby="investigation-facts-title">
        <h2 id="investigation-facts-title">对照原文，核对整理结果</h2>
        <p className="risk-note" role="note">左侧是系统整理的内容，右侧是引用的原文。请确认是否说的是同一岗位，有没有遗漏共同要求、例外或后续更正。</p>
        <EvidenceCheckSummary check={task.evidence_check} history={task.evidence_check_history} />
        <ReviewBrowser items={task.facts.map((fact, index) => ({ fact, index }))} label="原文对照"
          searchText={({ fact }) => `${entityNames.get(fact.entity_id) ?? "公告条件"} ${labels[fact.field] ?? fact.field} ${fact.value ?? ""} ${fact.note ?? ""}`}
          needsAttention={({ fact }) => fact.status !== "CONFIRMED" || !fact.evidence.length || !!fact.note}>
          {visible => <div className="candidate-list">{visible.map(({ fact, index }) => <article className="candidate-card" key={index}>
            <h3>{entityNames.get(fact.entity_id) ?? "公告条件 / 待确认归属"}</h3>
            <div className="candidate-grid"><div><small>系统整理 · 待你核对</small><h4>{labels[fact.field] ?? fact.field}</h4><p>{fact.value ?? "未知 / 未提供"}</p><span className="status-badge">{factStatuses[fact.status] ?? "待核对"}</span>
              {fact.note ? <div className="risk-note"><strong>调查备注（待人工核对）</strong><p>{fact.note}</p></div> : null}
            </div>
              <div>{fact.evidence.length ? fact.evidence.map((evidence, evidenceIndex) => <blockquote className="official-evidence-block" key={`${evidence.artifact_id}-${evidenceIndex}`}>
                <small>原文怎么说</small><p>{evidence.quote || "未提供引文"}</p>
                <footer><p>{readable(evidence.locator)}</p><EvidenceCheckDetail evidence={evidence} receipt={task.evidence_check?.references.find((item) => item.fact_index === task.facts.indexOf(fact) && item.reference_index === evidenceIndex)} />
                  {materialIds.has(evidence.artifact_id) ? <a href={materialPath(task.task_id, evidence.artifact_id)}>下载原件 · {evidence.artifact_id}</a> : <p className="form-alert">关联原件尚不可下载</p>}
                </footer>
              </blockquote>) : <p className="form-alert">缺少关联证据，保持未知并补充核对。</p>}</div>
            </div>
          </article>)}</div>}
        </ReviewBrowser>
        {!task.facts.length ? <p>尚无可展示的字段证据。</p> : null}
      </section>
      <section className="human-test-panel" aria-labelledby="investigation-materials-title">
        <h2 id="investigation-materials-title">已保存的调查材料</h2>
        <p>来源地址由调查服务提供，请打开核对文件是否对应。文件已保存不代表来源与内容已获确认。</p>
        {task.materials.length ? <ul className="human-test-run-list">{task.materials.map((material) => <li key={material.artifact_id}>
          <strong>{materialName(material)}</strong><div><a className="button button-secondary" href={materialPath(task.task_id, material.artifact_id)}>下载原件 · {materialName(material)}</a>{safeOfficialUrl(material.url) ? <a href={safeOfficialUrl(material.url)} target="_blank" rel="noopener noreferrer">核对来源地址</a> : <span>来源地址不可用</span>}</div>
          <small>{fileTypes[material.media_type] ?? "官方原件"} · {material.size_bytes.toLocaleString("zh-CN")} 字节</small>
          <details><summary>文件完整性标识</summary><code className="investigation-hash">SHA-256：{material.sha256}</code></details>
        </li>)}</ul> : <p>尚无已保存的原件。任务登记或远端结束均不代表文件已交付。</p>}
      </section>
    </>
  );
}

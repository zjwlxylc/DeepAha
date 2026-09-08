import type { EvidenceVerification, InvestigationEvidenceCheck, InvestigationFact } from "../../lib/investigations";

const content: Record<string, string> = { FOUND: "找到原文", NOT_FOUND: "可靠范围内未找到", NOT_ESTABLISHED: "读取依据不足" };
const locator: Record<string, string> = { VERIFIED: "声明定位成立", UNBOUND: "尚未绑定", UNSUPPORTED: "定位方式未支持", INVALID: "定位无效", MISMATCH: "声明定位不符" };
const verdicts = { PASS: "通过", FAIL: "失败", UNVERIFIED: "待核验" };

export function EvidenceCheckSummary({ check, history }: { check?: InvestigationEvidenceCheck | null; history?: InvestigationEvidenceCheck[] }) {
  if (!check) return <p>尚未生成持久化核验回执。历史布尔结果不代表已完成新版核验。</p>;
  return <div className="risk-note">
    <p>机械核验：{verdicts[check.verdict]} · 通过 {check.counts.PASS} / 失败 {check.counts.FAIL} / 待核验 {check.counts.UNVERIFIED}</p>
    <p>此回执不批准字段事实；待核验不计为通过或错误。</p>
    <details><summary>核验版本与历史</summary>
      {(history?.length ? history : [check]).map((item) => <p key={item.check_id}><code className="investigation-hash">{item.check_id} · {item.created_at} · {verdicts[item.verdict]} · SHA-256 {item.result_hash}</code></p>)}
    </details>
  </div>;
}

export function EvidenceCheckDetail({ evidence, receipt }: {
  evidence: InvestigationFact["evidence"][number];
  receipt?: InvestigationEvidenceCheck["references"][number];
}) {
  const result: EvidenceVerification | null | undefined = receipt?.verification ?? evidence.verification;
  if (!result) return <p>{evidence.mechanically_verified ? "旧版回执：机械核验通过；新版内容、定位和持久绑定尚未核验" : "旧版回执：原件与定位尚未完成机械核验"}</p>;
  return <>
    <p>内容：{content[result.content_support] ?? result.content_support} · 定位：{locator[result.declared_locator] ?? result.declared_locator}</p>
    <p>持久证据：{receipt?.persistent_binding ? "已关联 EvidenceRef" : "尚未关联"} · {receipt ? verdicts[receipt.verdict] : "尚未生成持久化回执"}</p>
    <details><summary>核验依据与候选位置</summary>
      <p>检查器 {result.verifier_version} · 精度 {result.precision} · 候选绑定 {result.binding}</p>
      <p>Reader：{result.reader ? `${result.reader.name} / ${result.reader.version} / ${result.reader.parse_contract} / ${result.reader.comparison_version}` : "格式尚未支持"}</p>
      <code className="investigation-hash">表示 SHA-256：{result.representation_sha256 ?? "未生成"}</code>
      {result.matches.map((match, index) => <p key={index}><code className="investigation-hash">{match.projection_id} · {match.source_spans.map((span) => `${span.origin_id} [${span.start}, ${span.end})`).join("；")}</code></p>)}
      {!!result.matches.length && <p>位置为 Reader 的原文字符范围，非原文件字节偏移。</p>}
      {receipt?.persistent_binding && <code className="investigation-hash">EvidenceRef：{receipt.persistent_binding.evidence_ref_id} · Parse：{receipt.persistent_binding.document_parse_key}</code>}
      {!!result.reason_codes.length && <p>原因：{result.reason_codes.join("、")}</p>}
      {receipt?.binding_reason && <p>绑定原因：{receipt.binding_reason}</p>}
    </details>
  </>;
}

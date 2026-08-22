import Link from "next/link";

import {
  opportunityChangeLabel,
  opportunityStatusLabel,
  opportunityTypeLabel,
} from "../../../components/opportunity-card";
import TrustFact from "../../../components/trust-fact";
import {
  formatDate,
  formatDateTime,
  getPublicOpportunity,
  type JsonValue,
} from "../../../lib/public-opportunities";

interface OpportunityDetailPageProps {
  params: Promise<{ publicId: string }>;
}

function displayValue(value: JsonValue): string {
  if (value === null) {
    return "无";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function locatorText(locatorValue: string | null, locatorPayload: Record<string, JsonValue> | null) {
  if (locatorPayload) {
    return JSON.stringify(locatorPayload);
  }
  return locatorValue ?? "未提供定位";
}

export default async function OpportunityDetailPage({ params }: OpportunityDetailPageProps) {
  const { publicId } = await params;
  const opportunity = await getPublicOpportunity(publicId);
  return (
    <main id="main-content" className="page-shell">
      <nav className="breadcrumbs" aria-label="面包屑">
        <Link href="/opportunities">公开机会</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">机会详情</span>
      </nav>

      {opportunity.data_label === "LICENSE_SAFE_FIXTURE" ? (
        <aside className="fixture-notice" aria-label="数据证据边界">
          本页是固定合成许可安全夹具，仅用于工程验证，不代表真实 Gold 机会。
        </aside>
      ) : null}

      <header className="detail-heading">
        <div className="card-heading-row">
          <p className="category-label">{opportunityTypeLabel(opportunity.type)}</p>
          <span className={`status-badge status-${opportunity.status.toLowerCase()}`}>
            {opportunityStatusLabel(opportunity.status)}
          </span>
        </div>
        <h1>{opportunity.title}</h1>
        <p className="stable-id">{opportunity.public_id}</p>
        {opportunity.change_markers.length > 0 ? (
          <ul className="change-markers" aria-label="变化标记">
            {opportunity.change_markers.map((marker) => (
              <li key={marker}>{opportunityChangeLabel(marker)}</li>
            ))}
          </ul>
        ) : null}
      </header>

      <section className="detail-grid" aria-label="机会可信字段">
        <div className="detail-panel">
          <h2>当前可信字段</h2>
          <dl className="detail-facts">
            <TrustFact label="发布单位">{opportunity.issuer_name}</TrustFact>
            <TrustFact label="地域">
              {[opportunity.jurisdiction, ...opportunity.locations].join(" · ")}
            </TrustFact>
            <TrustFact label="发布时间">
              <time dateTime={opportunity.published_at}>
                {formatDateTime(opportunity.published_at)}
              </time>
            </TrustFact>
            <TrustFact label="截止时间">
              <time dateTime={opportunity.deadline}>{formatDate(opportunity.deadline)}</time>
            </TrustFact>
            <TrustFact label="DeepAha 最后核验">
              <time dateTime={opportunity.last_verified_at}>
                {formatDateTime(opportunity.last_verified_at)}
              </time>
            </TrustFact>
            <TrustFact label="当前版本">v{opportunity.current_version}</TrustFact>
          </dl>
        </div>
        <aside className="official-panel" aria-labelledby="official-title">
          <h2 id="official-title">官方入口</h2>
          <p>报名、申请或政策申领请始终以官方页面为准。</p>
          <a
            className="button button-primary"
            href={opportunity.application_url}
            target="_blank"
            rel="noreferrer"
          >
            打开官方入口
          </a>
          {opportunity.attachment_urls.length > 0 ? (
            <ul className="official-links" aria-label="官方附件">
              {opportunity.attachment_urls.map((url, index) => (
                <li key={url}>
                  <a href={url} target="_blank" rel="noreferrer">
                    官方附件 {index + 1}
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p>当前没有单独附件。</p>
          )}
        </aside>
      </section>

      <section className="evidence-section" aria-labelledby="evidence-title">
        <div className="section-heading">
          <p className="section-kicker">EvidenceRef</p>
          <h2 id="evidence-title">关键字段证据</h2>
          <p>以下定位指向已保存的证据身份；外链打开对应官方原文。</p>
        </div>
        <div className="evidence-grid">
          {opportunity.key_evidence.map((evidence) => (
            <article
              className="evidence-card"
              aria-label={`字段证据 ${evidence.field_path}`}
              key={evidence.field_path}
            >
              <h3>{evidence.field_path}</h3>
              <p>
                EvidenceRef：<code>{evidence.evidence_ref_id}</code>
              </p>
              <p>
                Document：<code>{evidence.document_id}</code>
              </p>
              <p>
                定位：<code>{locatorText(evidence.locator_value, evidence.locator_payload)}</code>
              </p>
              <p>证据级别：{evidence.authority}</p>
              <a href={evidence.official_url} target="_blank" rel="noreferrer">
                查看官方证据
              </a>
            </article>
          ))}
        </div>
      </section>

      <section className="history-section" aria-labelledby="history-title">
        <div className="section-heading">
          <p className="section-kicker">Opportunity History</p>
          <h2 id="history-title">版本与变化历史</h2>
        </div>
        <ol className="timeline" aria-label="机会变化历史">
          {opportunity.history.map((event) => (
            <li key={event.event_id}>
              <div className="timeline-marker" aria-hidden="true" />
              <article>
                <div className="timeline-heading">
                  <h3>{opportunityChangeLabel(event.event_type)}</h3>
                  <time dateTime={event.detected_at}>{formatDateTime(event.detected_at)}</time>
                </div>
                <p>
                  版本 {event.from_version ?? "起始"} → {event.to_version}
                </p>
                <ul>
                  {event.changes.map((change) => (
                    <li key={change.field_path}>
                      <code>{change.field_path}</code>：{displayValue(change.before)} →{" "}
                      {displayValue(change.after)}
                    </li>
                  ))}
                </ul>
                <a href={event.official_url} target="_blank" rel="noreferrer">
                  查看本次变化的官方证据
                </a>
              </article>
            </li>
          ))}
        </ol>
      </section>

      <section className="fit-entry" aria-labelledby="fit-entry-title">
        <div>
          <p className="section-kicker">个人判断入口</p>
          <h2 id="fit-entry-title">想知道自己是否适合？</h2>
          <p>进入受控的最小画像、资格四态与个人行动流程；缺失信息会明确显示为未知。</p>
        </div>
        <Link className="button button-secondary" href={`/opportunities/${publicId}/fit-check`}>
          判断我是否适合
        </Link>
      </section>
    </main>
  );
}

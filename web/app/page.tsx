import Link from "next/link";


export default function Home() {
  return (
    <main id="main-content" className="page-shell">
      <section className="home-hero" aria-labelledby="home-title">
        <p className="eyebrow">DeepAha 青年机会智能系统</p>
        <h1 id="home-title">公开机会观测站：先看证据，再做判断</h1>
        <p className="hero-copy">
          这里展示经治理的机会身份、当前状态、关键时间、官方入口、证据定位与变化历史。
          公开结果只按确定性规则排序，不使用个性化结论或营销数字。
        </p>
        <div className="hero-actions">
          <Link className="button button-primary" href="/opportunities">
            浏览公开机会
          </Link>
          <a className="button button-secondary" href="#trust-fields">
            了解可信字段
          </a>
        </div>
      </section>
      <section id="trust-fields" className="trust-principles" aria-labelledby="trust-title">
        <div>
          <p className="section-kicker">公开可信层</p>
          <h2 id="trust-title">每条重要信息都能回到来源</h2>
        </div>
        <ul className="principle-grid">
          <li>
            <strong>稳定机会身份</strong>
            <span>同一机会的正文、附件和更正不会被当作多个孤立页面。</span>
          </li>
          <li>
            <strong>官方证据回链</strong>
            <span>关键条件展示 EvidenceRef 定位，并提供官方原文入口。</span>
          </li>
          <li>
            <strong>变化可追踪</strong>
            <span>更正、延期、附件替换与状态变化按版本形成时间线。</span>
          </li>
        </ul>
      </section>
    </main>
  );
}

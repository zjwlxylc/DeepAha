import type { Metadata } from "next";
import Link from "next/link";

import OpportunityCard from "../../components/opportunity-card";
import {
  listPublicOpportunities,
  normalizedSearchParams,
  opportunitiesHref,
  type SearchParams,
} from "../../lib/public-opportunities";

export const metadata: Metadata = {
  title: "公开机会观测站",
};

const typeOptions = [
  ["YOUTH_POLICY_BENEFIT", "青年政策权益"],
  ["PUBLIC_INSTITUTION_JOB", "事业单位招聘"],
  ["STATE_OWNED_ENTERPRISE_JOB", "国央企校招"],
  ["GRASSROOTS_PROGRAM", "基层项目"],
  ["COMPETITION", "竞赛"],
  ["RESEARCH_PROGRAM", "科研计划"],
  ["SCHOLARSHIP", "奖学金"],
  ["YOUTH_DEVELOPMENT_PROGRAM", "青年成长计划"],
] as const;

const statusOptions = [
  ["OPEN", "报名中"],
  ["CLOSING_SOON", "即将截止"],
  ["CLOSED", "已结束"],
  ["CANCELLED", "已取消"],
  ["SUPERSEDED", "已被更正替代"],
  ["UNKNOWN", "状态待核对"],
] as const;

interface OpportunitiesPageProps {
  searchParams: Promise<SearchParams>;
}

export default async function OpportunitiesPage({ searchParams }: OpportunitiesPageProps) {
  const query = normalizedSearchParams(await searchParams);
  const result = await listPublicOpportunities(query);
  const hasFixture = result.data_labels.includes("LICENSE_SAFE_FIXTURE");
  return (
    <main id="main-content" className="page-shell">
      <header className="page-heading">
        <p className="eyebrow">Public Trust Layer · 只读</p>
        <h1>公开机会观测站</h1>
        <p>
          用有限筛选查看经治理的机会。结果按确定性规则排序，不使用个性化排名。
        </p>
      </header>

      {hasFixture ? (
        <aside className="fixture-notice" aria-label="数据证据边界">
          当前展示固定合成许可安全夹具，仅用于工程验证，不是真实 Gold 机会，也不构成发布资格证据。
        </aside>
      ) : null}

      <form className="filter-panel" role="search" method="get" action="/opportunities">
        <div className="filter-search">
          <label htmlFor="opportunity-search">搜索机会</label>
          <input
            id="opportunity-search"
            name="q"
            type="search"
            maxLength={100}
            defaultValue={query.q ?? ""}
            placeholder="名称、发布单位或稳定 ID"
          />
        </div>
        <div>
          <label htmlFor="opportunity-type">机会类别</label>
          <select id="opportunity-type" name="type" defaultValue={query.type ?? ""}>
            <option value="">全部类别</option>
            {typeOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="opportunity-status">当前状态</label>
          <select id="opportunity-status" name="status" defaultValue={query.status ?? ""}>
            <option value="">全部状态</option>
            {statusOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="opportunity-region">地域</label>
          <input
            id="opportunity-region"
            name="region"
            maxLength={80}
            defaultValue={query.region ?? ""}
            placeholder="例如：浙江"
          />
        </div>
        <div>
          <label htmlFor="opportunity-sort">排序</label>
          <select id="opportunity-sort" name="sort" defaultValue={query.sort ?? "PUBLISHED_DESC"}>
            <option value="PUBLISHED_DESC">最新发布优先</option>
            <option value="DEADLINE_ASC">最早截止优先</option>
          </select>
        </div>
        <div className="filter-actions">
          <button className="button button-primary" type="submit">
            应用筛选
          </button>
          <Link className="button button-secondary" href="/opportunities">
            清除
          </Link>
        </div>
      </form>

      <section className="results-section" aria-labelledby="results-title">
        <div className="results-heading">
          <h2 id="results-title">公开结果</h2>
          <p aria-live="polite">本页 {result.count} 条</p>
        </div>
        {result.items.length === 0 ? (
          <div className="empty-state" role="status">
            <h3>没有找到符合条件的公开机会</h3>
            <p>可以减少筛选条件，或稍后查看新的经治理候选。</p>
            <Link className="button button-secondary" href="/opportunities">
              查看全部
            </Link>
          </div>
        ) : (
          <div className="opportunity-grid">
            {result.items.map((opportunity) => (
              <OpportunityCard key={opportunity.public_id} opportunity={opportunity} />
            ))}
          </div>
        )}
        {result.next_cursor ? (
          <nav className="pagination" aria-label="公开机会分页">
            <Link className="button button-secondary" href={opportunitiesHref(query, result.next_cursor)}>
              下一页
            </Link>
          </nav>
        ) : null}
      </section>
    </main>
  );
}

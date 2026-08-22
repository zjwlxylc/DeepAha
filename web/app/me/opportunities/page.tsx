import type { Metadata } from "next";
import Link from "next/link";

import PersonalOpportunityCard from "../../../components/personal-opportunity-card";
import { getPersonalPriorities } from "../../../lib/personal-opportunities";

export const metadata: Metadata = { title: "个人行动台" };

export default async function PersonalOpportunitiesPage() {
  const priorities = await getPersonalPriorities();
  return (
    <main id="main-content" className="page-shell personal-shell">
      <header className="page-heading personal-heading">
        <p className="eyebrow">Personal Action · 个人行动</p>
        <h1>未来 90 天行动台</h1>
        <p>最多展示 3 个优先机会。资格四态先于软偏好，排序不改变硬资格。</p>
      </header>
      <aside className="fixture-notice" aria-label="数据证据边界">
        当前工程流程使用固定合成许可安全夹具，不是真人指标、真实 Gold 机会或发布资格证据。
      </aside>
      <p>
        <Link className="button button-secondary" href="/me/reminders">
          查看截止变化提醒测试收件箱
        </Link>
      </p>
      {priorities.items.length === 0 ? (
        <div className="empty-state" role="status">
          <h2>暂时没有需要优先处理的机会</h2>
          <p>可能是 90 天窗口内没有可行动结果，或机会尚缺少精确 RuleSet。</p>
          <Link className="button button-secondary" href="/profile">检查或补充画像</Link>
        </div>
      ) : (
        <section className="personal-priority-list" aria-label="最多三个优先机会">
          {priorities.items.slice(0, 3).map((item) => (
            <PersonalOpportunityCard item={item} key={item.opportunity.public_id} />
          ))}
        </section>
      )}
      {priorities.omitted_rule_set_count > 0 ? (
        <p className="risk-note" role="note">
          另有 {priorities.omitted_rule_set_count} 个公开候选缺少精确规则版本，未进入个人结论。
        </p>
      ) : null}
    </main>
  );
}

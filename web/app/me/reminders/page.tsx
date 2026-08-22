import type { Metadata } from "next";

import ReminderInboxCard from "../../../components/reminder-inbox-card";
import ReminderPreferenceToggle from "../../../components/reminder-preference-toggle";
import { getDeadlineReminderPreference, getReminderInbox } from "../../../lib/reminders";

export const metadata: Metadata = { title: "截止变化提醒测试收件箱" };

export default async function ReminderPage() {
  const [preference, inbox] = await Promise.all([
    getDeadlineReminderPreference(),
    getReminderInbox(),
  ]);
  return (
    <main id="main-content" className="page-shell personal-shell reminder-shell">
      <header className="page-heading personal-heading">
        <p className="eyebrow">Reminder Test · 提醒测试</p>
        <h1>截止变化提醒测试收件箱</h1>
        <p>只承接已收藏机会的精确截止日期变化，保留版本、事件与官方证据绑定。</p>
      </header>
      <aside className="fixture-notice" aria-label="提醒证据边界">
        当前只使用固定合成许可安全夹具验证工程投递，不是真人打开、投诉、留存、行动或发布资格证据。
      </aside>
      <ReminderPreferenceToggle preference={preference} />
      {!preference?.enabled ? (
        <p className="risk-note" role="note">当前未开启截止日期变化提醒。</p>
      ) : null}
      <section className="reminder-inbox" aria-labelledby="reminder-inbox-title">
        <div className="results-heading">
          <h2 id="reminder-inbox-title">测试收件箱</h2>
          <p>{inbox.count} 条不可变投递记录</p>
        </div>
        {inbox.items.length === 0 ? (
          <div className="empty-state" role="status">
            <h3>测试收件箱还是空的</h3>
            <p>只有精确截止变化通过公开治理且用户控制仍有效时，才会出现记录。</p>
          </div>
        ) : (
          <div className="reminder-inbox-list">
            {inbox.items.map((entry) => (
              <ReminderInboxCard entry={entry} key={entry.inbox_entry_id} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

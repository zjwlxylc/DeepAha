import Link from "next/link";

import type { ReminderInboxEntry } from "../lib/reminders";

const directionLabels = {
  ADVANCED: "提前",
  EXTENDED: "延后",
} as const;

function detectedLabel(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function ReminderInboxCard({ entry }: { entry: ReminderInboxEntry }) {
  return (
    <article className="reminder-inbox-card">
      <div className="card-heading-row">
        <h2>{entry.opportunity_title}</h2>
        <span className={`deadline-direction direction-${entry.direction.toLowerCase()}`}>
          {directionLabels[entry.direction]}
        </span>
      </div>
      <p className="stable-id">
        事件 {entry.event_id} · 版本 {entry.from_version} → {entry.to_version}
      </p>
      <dl className="deadline-change-facts">
        <div><dt>原截止日期</dt><dd><time dateTime={entry.old_closes_on}>{entry.old_closes_on}</time></dd></div>
        <div><dt>新截止日期</dt><dd><time dateTime={entry.new_closes_on}>{entry.new_closes_on}</time></dd></div>
        <div><dt>系统识别时间</dt><dd><time dateTime={entry.detected_at}>{detectedLabel(entry.detected_at)}</time></dd></div>
      </dl>
      <div className="evidence-links reminder-evidence-links" aria-label="截止变化官方证据">
        <a href={entry.previous_official_url} target="_blank" rel="noreferrer">
          查看变更前官方证据
        </a>
        <a href={entry.current_official_url} target="_blank" rel="noreferrer">
          查看当前官方证据
        </a>
      </div>
      <Link className="button button-primary" href={entry.personal_detail_path}>
        回到个人行动
      </Link>
    </article>
  );
}

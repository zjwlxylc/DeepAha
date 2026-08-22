import { toggleDeadlineReminderAction } from "../app/reminder-actions";
import type { ReminderPreferenceSnapshot } from "../lib/reminders";

export default function ReminderPreferenceToggle({
  preference,
}: {
  preference: Pick<ReminderPreferenceSnapshot, "enabled" | "cadence" | "target"> | null;
}) {
  const enabled = preference?.enabled === true;
  return (
    <section className="reminder-preference" aria-labelledby="reminder-preference-title">
      <p className="section-kicker">独立提醒开关</p>
      <h2 id="reminder-preference-title">收藏不等于开启提醒</h2>
      <p>
        只有你独立开启后，系统才会为已收藏机会生成截止日期变化提醒。关闭后，待投递提醒会被抑制。
      </p>
      <dl className="compact-facts reminder-fixed-settings">
        <div><dt>频率</dt><dd>尽快（精确版本通过治理后）</dd></div>
        <div><dt>投递端</dt><dd>站内测试收件箱</dd></div>
      </dl>
      <form action={toggleDeadlineReminderAction}>
        <label className="check-label" htmlFor="deadline-reminder-enabled">
          <input
            id="deadline-reminder-enabled"
            name="enabled"
            type="checkbox"
            defaultChecked={enabled}
          />
          开启截止日期变化提醒
        </label>
        <button className="button button-secondary" type="submit">
          保存提醒设置
        </button>
      </form>
      <p className="field-help">
        当前状态：{enabled ? "已开启" : "未开启"}。此开关不会自动随收藏变化。
      </p>
    </section>
  );
}

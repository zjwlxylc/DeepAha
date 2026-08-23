import {
  addMaterialAction,
  openOfficialLinkAction,
  setActionStatusAction,
  toggleSavedAction,
} from "../app/personal-actions";
import type { PersonalActionSnapshot } from "../lib/personal-opportunities";

const stateLabels = {
  NOT_STARTED: "尚未开始",
  PREPARING: "准备中",
  APPLIED: "已申请",
  COMPLETED: "已完成",
  DISMISSED: "不再处理",
} as const;

export default function ActionPanel({ publicId, action }: { publicId: string; action: PersonalActionSnapshot | null }) {
  const snapshotKey = action?.action_snapshot_id ?? "no-action";
  return (
    <aside className="action-panel" aria-labelledby="action-title">
      <p className="section-kicker">个人行动</p>
      <h2 id="action-title">下一步怎么做</h2>
      <p>当前状态：{action ? stateLabels[action.state] : "尚未开始"}</p>
      <div className="action-forms">
        <form action={toggleSavedAction} key={`saved-${snapshotKey}`}>
          <input type="hidden" name="public_id" value={publicId} />
          <input type="hidden" name="saved" value={action?.saved ? "false" : "true"} />
          <button className="button button-secondary" type="submit">
            {action?.saved ? "取消保存" : "保存机会"}
          </button>
        </form>
        <form action={setActionStatusAction} key={`status-${snapshotKey}`}>
          <input type="hidden" name="public_id" value={publicId} />
          <label>
            行动状态
            <select name="state" defaultValue={action?.state ?? "NOT_STARTED"}>
              {Object.entries(stateLabels).map(([value, label]) => (
                <option value={value} key={value}>{label}</option>
              ))}
            </select>
          </label>
          <button className="button button-secondary" type="submit">更新状态</button>
        </form>
        <form action={addMaterialAction} key={`materials-${snapshotKey}`}>
          <input type="hidden" name="public_id" value={publicId} />
          <label>
            新增材料项
            <input name="material_label" maxLength={80} required />
          </label>
          <label>
            计划日期（可跳过）
            <input name="material_due_on" type="date" />
          </label>
          <button className="button button-secondary" type="submit">保存材料计划</button>
        </form>
        <form action={openOfficialLinkAction}>
          <input type="hidden" name="public_id" value={publicId} />
          <button className="button button-primary" type="submit">记录并打开官方入口</button>
        </form>
      </div>
      {action?.material_items.length ? (
        <ul className="material-list" aria-label="材料计划">
          {action.material_items.map((item) => (
            <li key={item.material_item_id}>
              {item.completed ? "已完成" : "待准备"} · {item.label}
              {item.due_on ? ` · 计划日期 ${item.due_on}` : null}
            </li>
          ))}
        </ul>
      ) : null}
    </aside>
  );
}

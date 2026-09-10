import Link from "next/link";
import type { InvestigationTask } from "../../lib/investigations";
import { groupPreviewPath } from "../../lib/group-sources";

export default function GroupSourceLinks({ task }: { task: InvestigationTask }) {
  const groups = task.binding_entities?.filter(entity => entity.kind === "unit") ?? [];
  if (!groups.length) return null;
  const ready = task.status === "APPROVED" && task.entity_binding?.bundle_status === "FROZEN";
  return <section className="human-test-panel" aria-labelledby="group-source-links-title">
    <h2 id="group-source-links-title">单位组来源与成员</h2>
    <p>按原组完整查看成员及当前身份关联。登记组来源不会批准组条件，也不会改变岗位资格。</p>
    {ready ? <ul>{groups.map(group => <li key={group.id}><Link prefetch={false} href={groupPreviewPath({ task_id: task.task_id, entity_id: group.id })}>查看组来源：{group.name}</Link></li>)}</ul>
      : <p>请先核对内部材料并确认当前机会归属，冻结来源后再查看组来源。</p>}
  </section>;
}

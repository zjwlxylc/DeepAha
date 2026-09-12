import type { InvestigationTask } from "../../lib/investigations";
import { investigationNextSteps, type InvestigationNextStep } from "../../lib/investigation-next-step";

const labels: Record<InvestigationNextStep["status"], string> = {
  ACTIONABLE: "当前可执行",
  DONE: "已完成",
  WAITING: "等待前置步骤",
  BLOCKED: "需要处理",
};

const anchorText: Record<string, string> = {
  dispatch: "前往发起区块",
  materials: "前往调查材料",
  documents: "前往文档准备",
  bindings: "前往归属确认",
  facts: "前往字段与规则审核",
  rules: "前往规则审核与条件快照入口",
};

/**
 * Server component: renders the "下一步 / 为什么不适用" navigation layer above the
 * existing evidence/review sections. It only reads the current task view and
 * links to in-page anchors, so the operator never has to paste an internal id.
 */
export default function NextSteps({ task }: { task: InvestigationTask }) {
  const steps = investigationNextSteps(task);
  const actionable = steps.find((current) => current.status === "ACTIONABLE");
  return (
    <section className="human-test-panel" aria-labelledby="investigation-next-steps-title">
      <h2 id="investigation-next-steps-title">下一步该做什么</h2>
      <p>按当前实际状态列出可执行步骤；等待、需要处理或已完成的步骤会说明原因。全程无需手动填写内部标识。</p>
      <p data-testid="next-step-summary" role="status">{actionable
        ? `当前下一步：${actionable.label}。`
        : "当前没有可执行的下一步；请先按下列原因处理或等待处理进程。"}</p>
      <ol className="human-test-run-list">
        {steps.map((current, index) => <li key={current.key} data-testid={`next-step-${current.key}`} data-status={current.status}>
          <div><span className="status-badge">{labels[current.status]}</span> <strong>{index + 1}. {current.label}</strong></div>
          {current.reason ? <p className="field-help">{current.reason}</p> : <p className="field-help">可点击下方入口继续，无需填写内部标识。</p>}
          {current.status !== "WAITING"
            ? <a href={current.href ?? current.anchor}>{current.href ? `查看${current.label}` : anchorText[current.key] ?? "前往对应区块"}</a>
            : null}
        </li>)}
      </ol>
      <details>
        <summary>如何进入范围预检</summary>
        <p>请先在规则审核区整理条件快照，再点击“查看条件快照”，进入跨层条件与范围预检。尚未完成的审核和未知条件会继续保留。</p>
      </details>
    </section>
  );
}

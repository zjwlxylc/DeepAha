"use client";

import { useActionState } from "react";
import { runtimeAction } from "../../app/review/investigations/runtime-actions";
import { dispatchReadiness, wmaStates, type InvestigationRuntime } from "../../lib/investigation-runtime";
import { formatDateTime } from "../../lib/public-opportunities";

export default function RuntimePanel({ initial }: { initial: InvestigationRuntime }) {
  const [state, action, pending] = useActionState(runtimeAction, { error: null });
  const current = state.result ?? initial;
  const readiness = dispatchReadiness(current);
  return <section className="human-test-panel" aria-labelledby="runtime-title" data-testid="investigation-runtime" data-authenticated="true">
    <h2 id="runtime-title">调查启动与就绪</h2>
    <p>登录已确认 · 数据库已连接 · {current.source_count ? `${current.source_count} 个可用来源` : "暂无可用来源，请查看下方来源说明"}</p>
    <p>{current.worker.state === "RUNNING" ? "调查处理进程运行中" : "调查处理进程未运行，请使用一键启动入口重新启动"}</p>
    {current.worker.updated_at ? <p className="field-help">进程最近响应：{formatDateTime(current.worker.updated_at)}</p> : null}
    <p>WMA：<strong>{pending || state.error ? "状态需要重新确认" : wmaStates[current.wma.state] ?? "状态无法确认"}</strong></p>
    {current.wma.sdk_available === false ? <p className="risk-note">缺少 WMA 连接组件，请重新运行一键启动入口安装依赖。</p> : null}
    {current.wma.agent_id ? <p>当前 Agent：{current.wma.agent_id} · 调用方：{current.wma.source_app}</p> : null}
    {current.wma.checked_at ? <p>上次检查：{formatDateTime(current.wma.checked_at)}</p> : null}
    {!pending && !state.error && current.wma.release ? <p>后台发布版本：{current.wma.release.release_version} · 后台模型：{current.wma.release.published_model}</p> : null}
    {current.wma.error_code ? <p className="risk-note">未能核验发布连接，请确认密钥权限、Agent 已发布且服务可用。诊断编号：{current.wma.error_code}</p> : null}
    {current.wma.state === "CHECK_EXPIRED" ? <p className="risk-note" data-testid="wma-expired-note">连接检查已过期，请点击「检查 WMA 发布连接」重新检查；新请求需重新检查；已明确发起的任务仍按发起时的配置执行。</p> : null}
    <p className={readiness.ready ? "field-help" : "risk-note"} data-testid="dispatch-readiness">{readiness.message}</p>
    <p className="field-help">是否发起调查由你在具体任务上明确点击决定；页面加载或刷新都不会自动发起。</p>
    <p className="field-help">连接检查只读取后台发布配置，不发起调查，不证明模型执行成功。模型沿用 WorkBuddy 后台配置，本页不修改。</p>
    <form action={action} className="card-actions"><button className="button button-secondary" name="operation" value="refresh" disabled={pending}>刷新就绪状态</button><button className="button button-secondary" name="operation" value="check" disabled={pending || !current.wma.revision}>检查 WMA 发布连接</button></form>
    <details><summary>配置 WMA 连接</summary><form action={action} className="human-test-form">
      <input type="hidden" name="operation" value="save" />
      <label>WMA 企业密钥<input type="password" name="api_key" required autoComplete="off" maxLength={4096} /></label>
      <label>已发布 Agent 标识<input name="agent_id" required defaultValue={current.wma.agent_id ?? ""} /></label>
      <label>调用方（source_app）<input name="source_app" required defaultValue={current.wma.source_app ?? "cloud-agent"} /></label>
      <p className="field-help">密钥由当前 Windows 账号加密保存在本机，不在页面读回。更换配置后需要重新检查连接。</p>
      <button className="button button-primary" disabled={pending}>保存 WMA 配置</button>
    </form></details>
    {pending ? <p role="status">正在更新，请稍候……</p> : null}
    {state.error ? <p role="alert">{state.error}</p> : state.message ? <p role="status">{state.message}</p> : null}
  </section>;
}

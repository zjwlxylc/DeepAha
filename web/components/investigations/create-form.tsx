"use client";

import Link from "next/link";
import { useActionState, useState } from "react";

import { createInvestigationAction, type InvestigationActionState } from "../../app/review/investigations/actions";
import type { InvestigationSource } from "../../lib/investigations";

const initialState: InvestigationActionState = { error: null, message: null, taskId: null };

export default function InvestigationCreateForm({ sources, requestKey }: { sources: InvestigationSource[]; requestKey: string }) {
  const [state, action, pending] = useActionState(createInvestigationAction, initialState);
  const [formKey] = useState(requestKey);
  const [values, setValues] = useState({ source_key: "", notice_url: "", brief: "", expected_artifact_urls: "", expected_entity_keys: "", wall_time_seconds: "600", calibration: true });
  const field = (key: Exclude<keyof typeof values, "calibration">) => ({ value: values[key], onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setValues({ ...values, [key]: event.target.value }) });
  return (
    <section className="human-test-panel" aria-labelledby="investigation-create-title">
      <h2 id="investigation-create-title">登记一项明确的公告调查</h2>
      <p className="field-help">登记不会访问官网或调用调查服务。执行由获授权的运维人员另行安排。</p>
      <form className="human-test-form" action={action} onReset={(event) => event.preventDefault()}>
        <input type="hidden" name="request_key" value={formKey} />
        <label>已批准来源
          <select name="source_key" {...field("source_key")} required>
            <option value="" disabled>请选择来源</option>
            {sources.map((source) => <option key={`${source.source_id}/${source.endpoint_id}`} value={`${source.source_id}/${source.endpoint_id}`}>{source.authority_name} · {source.url}</option>)}
          </select>
        </label>
        <label>明确公告地址<input name="notice_url" type="url" {...field("notice_url")} required placeholder="https://官方站点/具体公告" /></label>
        <p className="field-help">公告和附件仅支持所选来源已批准域名的 HTTPS 地址。</p>
        <label>调查说明<textarea name="brief" rows={5} maxLength={12000} {...field("brief")} required placeholder="说明需要调查的机会、全部子项和需要核对的条件。" /></label>
        <div className="human-test-form-grid">
          <label>预期官方附件地址（可选，每行一个）<textarea name="expected_artifact_urls" rows={4} {...field("expected_artifact_urls")} /></label>
          <label>预期岗位或子项标识（可选，每行一个）<textarea name="expected_entity_keys" rows={4} {...field("expected_entity_keys")} /></label>
        </div>
        <label>执行时间上限（秒）<input name="wall_time_seconds" type="number" min={60} max={1800} step={1} {...field("wall_time_seconds")} required /></label>
        <div className="human-test-checks"><label className="check-label"><input name="calibration" type="checkbox" checked={values.calibration} onChange={(event) => setValues({ ...values, calibration: event.target.checked })} />本任务用于校准或已讨论样本，不作为隐藏盲测</label></div>
        {!sources.length ? <p className="risk-note" role="note">当前没有可选的已批准来源，请先完成来源登记。</p> : null}
        {state.error ? <p className="form-alert" role="alert">{state.error}</p> : null}
        {state.message ? <p className="form-success" role="status">{state.message}</p> : null}
        {state.taskId ? <Link className="button button-secondary" href={`/review/investigations/${state.taskId}`}>查看已登记任务</Link> : null}
        <button className="button button-primary" type="submit" disabled={pending || !sources.length}>{pending ? "正在登记" : "登记调查任务"}</button>
      </form>
    </section>
  );
}

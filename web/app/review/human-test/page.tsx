import type { Metadata } from "next";
import Link from "next/link";

import DataManagement from "../../../components/human-test/data-management";
import ProviderConfigForm from "../../../components/human-test/provider-config-form";
import RunForm from "../../../components/human-test/run-form";
import {
  getLocalProviderStatus,
  getLocalRuns,
  getLocalSources,
} from "../../../lib/local-human-test";
import { formatDateTime } from "../../../lib/public-opportunities";

export const metadata: Metadata = { title: "本地人工测试控制台" };

export default async function HumanTestPage() {
  const [provider, sources, runs] = await Promise.all([
    getLocalProviderStatus(),
    getLocalSources(),
    getLocalRuns(),
  ]);
  return (
    <main id="main-content" className="page-shell human-test-shell">
      <header className="human-test-hero">
        <div>
          <p className="eyebrow">Local Human Test · 本地人工体验</p>
          <h1>从官方证据到人工批准的受控工作台</h1>
          <p>
            双击启动不会访问官网或模型。只有你在这里明确创建实时运行，系统才按页面展示的固定预算执行。
          </p>
        </div>
        <dl className="boundary-status-grid">
          <div><dt>工程状态</dt><dd>IMPLEMENTED</dd></div>
          <div><dt>Release Qualification</dt><dd>Release Qualification：NOT_STARTED</dd></div>
          <div><dt>真人证据</dt><dd>真人参与者：0</dd></div>
          <div><dt>本地发布标签</dt><dd>LOCAL_HUMAN_REVIEWED</dd></div>
        </dl>
      </header>
      <aside className="fixture-notice" aria-label="证据责任边界">
        这里用于负责人本人体验和人工检查；本地批准不等于 Gold、不等于生产发布，也不会替你批准重大资格判断。
      </aside>
      <p><Link className="button button-secondary" href="/review/investigations">官方机会调查：登记任务与核对原件</Link></p>
      <div className="human-test-dashboard-grid">
        <ProviderConfigForm status={provider} />
        <RunForm sources={sources} providerReady={provider.egress_ready && provider.configured} />
      </div>
      <section className="human-test-panel" aria-labelledby="recent-runs-title">
        <div className="human-test-panel-heading">
          <div>
            <p className="section-kicker">Recoverable state</p>
            <h2 id="recent-runs-title">最近运行</h2>
          </div>
          <span className="status-badge">{runs.length} 条</span>
        </div>
        {runs.length ? (
          <ol className="human-test-run-list">
            {runs.map((run) => (
              <li key={run.run_id}>
                <div>
                  <span className="status-badge">{run.mode}</span>
                  <strong>{run.status}</strong>
                </div>
                <Link href={`/review/human-test/runs/${run.run_id}`}>查看运行证据</Link>
                <small>
                  {run.provider} / {run.model_id} · 官网 {run.official_request_count}/9 · LLM {run.llm_call_count}/8 · {formatDateTime(run.updated_at)}
                </small>
              </li>
            ))}
          </ol>
        ) : <div className="empty-state"><h3>尚未创建运行</h3><p>启动本地环境本身不会产生外部调用。</p></div>}
      </section>
      <DataManagement />
    </main>
  );
}

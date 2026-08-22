"use client";

import Link from "next/link";

interface OpportunityDetailErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function OpportunityDetailError({ error, reset }: OpportunityDetailErrorProps) {
  void error;
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <p className="eyebrow">核对失败</p>
        <h1>暂时无法核对机会详情</h1>
        <p>当前没有展示未经核对的替代信息。请稍后重试或返回公开机会列表。</p>
        <div className="state-actions">
          <button className="button button-primary" type="button" onClick={reset}>
            重新加载
          </button>
          <Link className="button button-secondary" href="/opportunities">
            返回公开机会
          </Link>
        </div>
      </div>
    </main>
  );
}

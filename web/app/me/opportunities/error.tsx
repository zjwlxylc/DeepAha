"use client";

export default function PersonalOpportunitiesError({ reset }: { reset: () => void }) {
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <h1>个人行动台暂时不可用</h1>
        <p>没有用旧结果替代本次失败；请稍后重试。</p>
        <button className="button button-primary" type="button" onClick={reset}>重新加载</button>
      </div>
    </main>
  );
}

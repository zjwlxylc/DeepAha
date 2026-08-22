"use client";

interface OpportunitiesErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function OpportunitiesError({ error, reset }: OpportunitiesErrorProps) {
  void error;
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <p className="eyebrow">加载失败</p>
        <h1>暂时无法加载公开机会</h1>
        <p>没有把失败伪装成空结果。请稍后重试。</p>
        <button className="button button-primary" type="button" onClick={reset}>
          重新加载
        </button>
      </div>
    </main>
  );
}

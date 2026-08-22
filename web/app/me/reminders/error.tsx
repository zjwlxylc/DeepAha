"use client";

export default function ReminderError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  void error;
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <h1>截止变化提醒暂时不可用</h1>
        <p>没有把失败伪装成空收件箱，也不会显示其他用户记录。</p>
        <button
          className="button button-primary"
          type="button"
          onClick={reset}
        >
          重新加载
        </button>
      </div>
    </main>
  );
}

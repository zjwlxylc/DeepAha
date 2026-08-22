export default function ReviewQueueLoading() {
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state" role="status" aria-live="polite">
        <h1>正在读取受控审核队列</h1>
        <p>正在验证 reviewer 身份、用途与角色。</p>
      </div>
    </main>
  );
}

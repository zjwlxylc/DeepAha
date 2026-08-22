export default function FeedbackDetailLoading() {
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state" role="status" aria-live="polite">
        <h1>正在读取处理详情</h1>
        <p>只返回当前用户可见的公开状态与证据摘要。</p>
      </div>
    </main>
  );
}

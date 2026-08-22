export default function FeedbackListLoading() {
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state" role="status" aria-live="polite">
        <h1>正在读取纠错状态</h1>
        <p>只读取当前个人会话拥有的反馈记录。</p>
      </div>
    </main>
  );
}

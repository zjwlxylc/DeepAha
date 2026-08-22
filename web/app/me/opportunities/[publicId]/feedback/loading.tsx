export default function FeedbackLoading() {
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state" role="status" aria-live="polite">
        <h1>正在核对纠错上下文</h1>
        <p>正在绑定当前匹配、机会版本、画像版本和官方 EvidenceRef。</p>
      </div>
    </main>
  );
}

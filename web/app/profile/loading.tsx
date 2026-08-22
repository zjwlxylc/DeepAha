export default function ProfileLoading() {
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state" role="status" aria-live="polite">
        <h1>正在读取你的最小画像</h1>
        <p>只加载当前用户被授权的画像快照。</p>
      </div>
    </main>
  );
}

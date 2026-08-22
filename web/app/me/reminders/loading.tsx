export default function ReminderLoading() {
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state" role="status" aria-live="polite">
        <h1>正在读取截止变化提醒</h1>
        <p>正在核对提醒偏好、精确版本和测试收件箱。</p>
      </div>
    </main>
  );
}

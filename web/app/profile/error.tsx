"use client";

export default function ProfileError({ reset }: { reset: () => void }) {
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <h1>画像暂时无法读取</h1>
        <p>未保存的输入不会被提交。请确认个人会话后重试。</p>
        <button className="button button-primary" type="button" onClick={reset}>重试</button>
      </div>
    </main>
  );
}

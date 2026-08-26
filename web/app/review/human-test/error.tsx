"use client";

export default function HumanTestError({ reset }: { reset: () => void }) {
  return (
    <main id="main-content" className="page-shell human-test-shell">
      <div className="route-state route-error" role="alert">
        <h1>本地人工测试控制台暂不可用</h1>
        <p>请确认一键启动器中的 API、数据库和 reviewer fixture 已就绪；错误详情不会回显 Provider 信息。</p>
        <button className="button button-primary" type="button" onClick={reset}>重新读取</button>
      </div>
    </main>
  );
}

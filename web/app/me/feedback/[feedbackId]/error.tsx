"use client";

import { useRouter } from "next/navigation";

export default function FeedbackDetailError({ reset }: { reset: () => void }) {
  const router = useRouter();
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <h1>处理详情不可用</h1>
        <p>记录不存在或不属于当前会话时，系统不会披露更多信息。</p>
        <button className="button button-primary" type="button" onClick={() => { reset(); router.refresh(); }}>
          重试
        </button>
      </div>
    </main>
  );
}

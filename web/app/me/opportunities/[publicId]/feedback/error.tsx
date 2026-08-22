"use client";

import { useRouter } from "next/navigation";

export default function FeedbackError({ reset }: { reset: () => void }) {
  const router = useRouter();
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <h1>纠错上下文暂时不可用</h1>
        <p>未绑定精确版本时不会提交反馈。请刷新个人机会解释后重试。</p>
        <button className="button button-primary" type="button" onClick={() => { reset(); router.refresh(); }}>
          重试
        </button>
      </div>
    </main>
  );
}

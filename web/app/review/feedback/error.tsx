"use client";

import { useRouter } from "next/navigation";

export default function ReviewQueueError({ reset }: { reset: () => void }) {
  const router = useRouter();
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <h1>审核队列不可用</h1>
        <p>reviewer 身份、用途或角色未通过；系统不会披露案件是否存在。</p>
        <button className="button button-primary" type="button" onClick={() => { reset(); router.refresh(); }}>
          重试
        </button>
      </div>
    </main>
  );
}

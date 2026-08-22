"use client";

import { useRouter } from "next/navigation";

export default function FeedbackListError({ reset }: { reset: () => void }) {
  const router = useRouter();
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <h1>纠错状态暂时无法读取</h1>
        <p>不会显示其他用户的记录。请确认个人会话后重试。</p>
        <button className="button button-primary" type="button" onClick={() => { reset(); router.refresh(); }}>
          重试
        </button>
      </div>
    </main>
  );
}

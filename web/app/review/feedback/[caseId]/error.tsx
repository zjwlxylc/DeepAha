"use client";

import { useRouter } from "next/navigation";

export default function ReviewCaseError({ reset }: { reset: () => void }) {
  const router = useRouter();
  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <h1>反馈案件不可用</h1>
        <p>案件不存在或当前 reviewer 无权访问时，系统返回相同的受控失败状态。</p>
        <button className="button button-primary" type="button" onClick={() => { reset(); router.refresh(); }}>
          重试
        </button>
      </div>
    </main>
  );
}

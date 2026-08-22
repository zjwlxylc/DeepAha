"use client";

import { useRouter } from "next/navigation";

export default function PersonalOpportunitiesError({ reset }: { reset: () => void }) {
  const router = useRouter();
  const retry = () => {
    reset();
    router.refresh();
  };

  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <h1>个人行动台暂时不可用</h1>
        <p>没有用旧结果替代本次失败；请稍后重试。</p>
        <button className="button button-primary" type="button" onClick={retry}>重新加载</button>
      </div>
    </main>
  );
}

"use client";

import { useRouter } from "next/navigation";

export default function PersonalDetailError({ reset }: { reset: () => void }) {
  const router = useRouter();
  const retry = () => {
    reset();
    router.refresh();
  };

  return (
    <main id="main-content" className="page-shell">
      <div className="route-state route-error" role="alert">
        <h1>个人解释暂时无法读取</h1>
        <p>当前不会把失败隐藏成确定资格。请重试或返回公开证据。</p>
        <button className="button button-primary" type="button" onClick={retry}>重试</button>
      </div>
    </main>
  );
}

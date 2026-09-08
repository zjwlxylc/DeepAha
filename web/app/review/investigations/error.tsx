"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

export default function InvestigationsError({ reset }: { reset: () => void }) {
  const router = useRouter();
  return <main id="main-content" className="page-shell"><div className="route-state route-error" role="alert"><h1>调查材料暂时无法读取</h1><p>请确认审核会话有效、当前账号有权限且服务已就绪。</p><div className="card-actions"><button className="button button-primary" type="button" onClick={() => { reset(); router.refresh(); }}>重试</button><Link className="button button-secondary" href="/review/investigations">返回任务列表</Link></div></div></main>;
}

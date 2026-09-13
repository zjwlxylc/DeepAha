"use client";

import Link from "next/link";

export default function ReviewError({ reset }: { reset: () => void }) {
  return <main className="page-shell guided-review" id="main-content"><section className="guided-card"><h1>这一步暂时没有读取成功</h1><p>网络、登录或材料版本可能已变化。已保存的记录仍保留；本次没有因此提交新判断。</p><button className="button button-primary" onClick={reset}>重新读取当前步骤</button><p>如果仍然无法打开，请从已登录的本地测试浏览器进入任务列表。</p><Link href="/review/investigations">返回任务列表</Link></section></main>;
}

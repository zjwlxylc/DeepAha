import Link from "next/link";


interface FitCheckBoundaryPageProps {
  params: Promise<{ publicId: string }>;
}

export default async function FitCheckBoundaryPage({ params }: FitCheckBoundaryPageProps) {
  const { publicId } = await params;
  return (
    <main id="main-content" className="page-shell boundary-page">
      <nav className="breadcrumbs" aria-label="面包屑">
        <Link href={`/opportunities/${publicId}`}>机会详情</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">个人判断边界</span>
      </nav>
      <section className="boundary-card" aria-labelledby="boundary-title">
        <p className="eyebrow">Phase 5 边界</p>
        <h1 id="boundary-title">个人判断尚未开放</h1>
        <p>
          真实画像采集、个人资格四态、个性化排序和行动台属于 Phase 6。当前页面不会收集你的画像，也不会计算个人资格。
        </p>
        <p>
          你仍可返回详情页核对官方条件、截止时间、证据定位与变化历史，并自行前往官方入口。
        </p>
        <Link className="button button-primary" href={`/opportunities/${publicId}`}>
          返回机会详情
        </Link>
      </section>
    </main>
  );
}

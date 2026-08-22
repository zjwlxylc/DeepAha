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
        <span aria-current="page">开始个人判断</span>
      </nav>
      <section className="boundary-card" aria-labelledby="boundary-title">
        <p className="eyebrow">Phase 6 · 受控入口</p>
        <h1 id="boundary-title">先完成最小画像</h1>
        <p>
          只询问当前资格与行动需要的信息。可选字段可跳过，缺失信息会保留为未知，不会默认成不符合。
        </p>
        <p>
          保存后将使用精确机会版本、RuleSet、画像快照与场景日期重放判断；软偏好只影响顺序。
        </p>
        <Link className="button button-primary" href={`/profile?returnTo=/me/opportunities/${publicId}`}>
          填写最小画像
        </Link>
      </section>
    </main>
  );
}

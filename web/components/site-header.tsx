import Link from "next/link";


export default function SiteHeader() {
  return (
    <header className="site-header">
      <div className="header-inner">
        <Link className="brand" href="/" aria-label="DeepAha 首页">
          <span>Deep</span>
          <span className="brand-aha">Aha</span>
        </Link>
        <p className="brand-tagline">Go Deep. Find the Aha.</p>
        <nav aria-label="主导航">
          <Link className="nav-link" href="/opportunities">
            公开机会
          </Link>
          <Link className="nav-link" href="/me/opportunities">
            个人行动
          </Link>
        </nav>
      </div>
    </header>
  );
}

import type { Metadata } from "next";
import Link from "next/link";

import { saveProfileAction } from "../personal-actions";
import ProfileForm from "../../components/profile-form";
import {
  getPersonalProfile,
  PersonalApiError,
  type UserStateSnapshot,
} from "../../lib/personal-opportunities";

export const metadata: Metadata = { title: "最小画像" };

export default async function ProfilePage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const { returnTo = "/me/opportunities" } = await searchParams;
  let initialState: UserStateSnapshot | null = null;
  try {
    initialState = await getPersonalProfile();
  } catch (error) {
    if (!(error instanceof PersonalApiError) || error.status !== 404) throw error;
  }
  return (
    <main id="main-content" className="page-shell personal-shell">
      <nav className="breadcrumbs" aria-label="面包屑">
        <Link href="/opportunities">公开机会</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">最小画像</span>
      </nav>
      <header className="page-heading personal-heading">
        <p className="eyebrow">Progressive Profile · 渐进画像</p>
        <h1>只回答当前判断需要的问题</h1>
        <p>所有字段都说明用途；可选项可跳过，缺失会显示为未知，而不是不符合。</p>
      </header>
      <ProfileForm initialState={initialState} action={saveProfileAction} returnTo={returnTo} />
    </main>
  );
}

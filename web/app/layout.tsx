import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import SiteHeader from "../components/site-header";
import "./globals.css";


export const metadata: Metadata = {
  title: {
    default: "DeepAha 公开机会观测站",
    template: "%s | DeepAha",
  },
  description: "查看机会来源、状态、核验时间、官方证据与变化历史。",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#0c3559",
  colorScheme: "light",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main-content">
          跳到主要内容
        </a>
        <SiteHeader />
        {children}
        <footer className="site-footer">
          <div className="footer-inner">
            <p>DeepAha · Go Deep. Find the Aha.</p>
            <p>公开信息以官方原文为准；DeepAha 核验时间与官方发布时间分别展示。</p>
          </div>
        </footer>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";


export const metadata: Metadata = {
  title: "DeepAha",
  description: "DeepAha 青年机会智能系统",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

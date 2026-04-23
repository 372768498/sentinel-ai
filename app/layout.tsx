import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Sentinel AI | 哨兵投研",
  description: "Bloomberg 风格股票风险雷达，15 秒内完成 10 维度投研分析并邮件投递 PDF。"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

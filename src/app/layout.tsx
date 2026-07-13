import type { Metadata } from "next";
import { Space_Grotesk } from "next/font/google";
import "./globals.css";
import { PrototypeFeedback } from "@/components/facefit/PrototypeFeedback";

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Face Fit — AI 모의면접 코칭",
  description: "이력서와 채용공고를 분석해 맞춤형 AI 모의면접과 4축 정밀 분석 리포트를 제공하는 Face Fit",
  openGraph: {
    title: "Face Fit — AI 모의면접 코칭",
    description: "이력서와 채용공고를 분석해 맞춤형 AI 모의면접과 4축 정밀 분석 리포트를 제공하는 Face Fit",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className={`${spaceGrotesk.variable} h-full antialiased`}>
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css"
        />
      </head>
      <body className="min-h-full flex flex-col">{children}<PrototypeFeedback /></body>
    </html>
  );
}

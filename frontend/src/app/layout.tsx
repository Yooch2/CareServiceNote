import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans_KR } from "next/font/google";
import "./globals.css";

const plex = IBM_Plex_Sans_KR({
  variable: "--font-plex",
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  preload: false,
});

export const metadata: Metadata = {
  // 화면마다 제목을 단다 (탭 전환·화면 읽기 프로그램용). 수급자 이름은 방문 기록(history)에 남지 않게 넣지 않는다
  title: { default: "돌봄수첩", template: "%s · 돌봄수첩" },
  description: "방문요양 음성 기록을 정리해 다음 돌봄으로 잇는 서비스",
};

export const viewport: Viewport = {
  themeColor: "#f3f6f4",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className={`${plex.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col text-[17px] leading-relaxed">{children}</body>
    </html>
  );
}

import type { Metadata } from "next";
import { Suspense } from "react";

import { RecipientManage } from "@/components/recipient-manage";
import { Loading } from "@/components/ui";

export const metadata: Metadata = { title: "수급자 관리" };

// 로그인 확인(AuthGate)이 끝난 뒤 브라우저에서 데이터를 불러오는 화면이라 즉시 이동 검사에서 제외한다
export const instant = false;

export default function RecipientManagePage() {
  return (
    <Suspense fallback={<Loading />}>
      <RecipientManage />
    </Suspense>
  );
}

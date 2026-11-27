import { Suspense } from "react";

import { RecordView } from "@/components/record-view";
import { Loading } from "@/components/ui";

// 로그인 확인(AuthGate)이 끝난 뒤 브라우저에서 데이터를 불러오는 화면이라 즉시 이동 검사에서 제외한다
export const instant = false;

export default function RecordDetailPage() {
  return (
    <Suspense fallback={<Loading />}>
      <RecordView />
    </Suspense>
  );
}

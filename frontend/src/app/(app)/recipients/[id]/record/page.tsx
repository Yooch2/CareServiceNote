import { Suspense } from "react";

import { Recorder } from "@/components/recorder";
import { Loading } from "@/components/ui";

export default function RecordPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Recorder />
    </Suspense>
  );
}

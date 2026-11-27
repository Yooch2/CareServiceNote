import { Suspense } from "react";

import { RecipientView } from "@/components/recipient-view";
import { Loading } from "@/components/ui";

export default function RecipientPage() {
  return (
    <Suspense fallback={<Loading />}>
      <RecipientView />
    </Suspense>
  );
}

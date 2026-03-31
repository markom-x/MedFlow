import { DashboardApp } from "@/components/dashboard/dashboard-app";

/** Evita che il segmento sia servito da cache statica: così `router.refresh()` può aggiornare i dati server/client tree. */
export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <div className="flex h-dvh min-h-0 w-full flex-col overflow-hidden bg-slate-50">
      <DashboardApp />
    </div>
  );
}

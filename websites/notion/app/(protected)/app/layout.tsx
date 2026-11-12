import { requireAuth } from "@/lib/auth";
import Sidebar from "@/app/app/_components/Sidebar";
import TabsBar from "@/app/app/_components/TabsBar";
import GuideDock from "@/app/app/_components/GuideDock";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  await requireAuth();

  return (
    <div className="h-screen overflow-hidden bg-[var(--bg)] print:h-auto print:overflow-visible">
      <div className="flex h-screen overflow-hidden print:block print:h-auto print:overflow-visible">
        <div className="print:hidden">
          <Sidebar />
        </div>
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden print:block print:overflow-visible">
          <div className="print:hidden">
            <TabsBar />
          </div>
          <main className="flex-1 overflow-y-auto overscroll-contain px-8 py-6 print:overflow-visible">
            {children}
          </main>
        </div>
      </div>
      <div className="print:hidden">
        <GuideDock />
      </div>
    </div>
  );
}

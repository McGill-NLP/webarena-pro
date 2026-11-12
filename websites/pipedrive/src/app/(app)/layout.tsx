import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { SessionProvider } from "next-auth/react";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session) redirect("/login");

  return (
    <SessionProvider session={session}>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex-1 min-w-0 flex flex-col">
          <Topbar />
          <main className="flex-1 p-6">{children}</main>
        </div>
      </div>
    </SessionProvider>
  );
}

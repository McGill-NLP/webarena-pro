import Link from "next/link";
import { redirect } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { getSessionUserId } from "@/lib/auth";

function displayNameFromEmail(email: string) {
  const localPart = email.split("@")[0] ?? "";
  const normalized = localPart.replace(/[._-]+/g, " ").trim();
  if (!normalized) return "User";
  return normalized.replace(/\b\w/g, (char) => char.toUpperCase());
}

export default async function ProfilePage() {
  const userId = getSessionUserId();
  if (!userId) {
    redirect("/login");
  }

  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: {
      email: true,
      createdAt: true,
      memberships: {
        include: { workspace: true },
        orderBy: { createdAt: "asc" },
      },
    },
  });
  if (!user) {
    redirect("/login");
  }

  return (
    <div className="mx-auto w-full max-w-[880px] space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-[-0.02em]">Profile</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">Personal account details and session actions.</p>
      </div>

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5">
        <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">User</h2>
        <div className="mt-4 space-y-2 text-sm">
          <p>
            <span className="text-[var(--muted)]">Display name:</span> {displayNameFromEmail(user.email)}
          </p>
          <p>
            <span className="text-[var(--muted)]">Email:</span> {user.email}
          </p>
          <p>
            <span className="text-[var(--muted)]">Joined:</span> {user.createdAt.toLocaleDateString()}
          </p>
        </div>
      </section>

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5">
        <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">Workspaces</h2>
        <ul className="mt-4 space-y-2">
          {user.memberships.map((membership) => (
            <li key={membership.id} className="rounded-md border border-[var(--line)] px-3 py-2 text-sm">
              {membership.workspace.name} ({membership.role})
            </li>
          ))}
        </ul>
      </section>

      <section className="flex flex-wrap gap-2">
        <Link href="/app/settings" className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm hover:bg-[var(--hover)]">
          Settings
        </Link>
        <a href="/api/logout" className="rounded-md border border-[#b42318] px-3 py-1.5 text-sm text-[#b42318] hover:bg-[var(--hover)]">
          Log out
        </a>
      </section>
    </div>
  );
}

import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import bcrypt from "bcryptjs";
import Database from "better-sqlite3";
import path from "path";

function getUser(email: string) {
  const dbPath = path.join(process.cwd(), "data", "crm.db");
  const db = new Database(dbPath);
  const user = db.prepare("SELECT * FROM users WHERE email = ?").get(email) as
    | { id: number; email: string; password: string; name: string }
    | undefined;
  db.close();
  return user;
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      authorize: async (credentials) => {
        const email = credentials?.email as string;
        const password = credentials?.password as string;
        if (!email || !password) return null;

        const user = getUser(email);
        if (!user) return null;

        const valid = await bcrypt.compare(password, user.password);
        if (!valid) return null;

        return { id: String(user.id), name: user.name, email: user.email };
      },
    }),
  ],
  session: { strategy: "jwt" },
  secret: process.env.AUTH_SECRET || "crm-secret-key-change-in-production",
  pages: {
    signIn: "/login",
  },
  callbacks: {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    jwt({ token, user }: { token: any; user: any }) {
      if (user?.id) token.id = user.id;
      return token;
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    session({ session, token }: { session: any; token: any }) {
      if (token.id) session.user.id = token.id as string;
      return session;
    },
  },
});

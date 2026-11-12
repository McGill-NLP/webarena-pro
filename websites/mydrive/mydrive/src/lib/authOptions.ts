import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import { PrismaAdapter } from "@next-auth/prisma-adapter";
import crypto from "crypto";
import { prisma } from "@/lib/db";

function hashPassword(password: string) {
  return crypto.createHash("sha256").update(password).digest("hex");
}

export const authOptions: NextAuthOptions = {
  adapter: PrismaAdapter(prisma),
  session: { strategy: "jwt" },
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = credentials?.email;
        const password = credentials?.password;
        if (!email || !password) return null;

        const user = await prisma.user.findUnique({ where: { email } });
        if (!user?.password) return null;

        if (user.password !== hashPassword(password)) return null;
        return {
          id: user.id,
          email: user.email,
          name: user.name ?? "",
          username: user.username,
        };
      },
    }),
  ],
  // Keep in sync with the inline NextAuth config in app/api/auth/[...nextauth]/
  // route.ts — API routes rely on getServerSession(authOptions).user.id.
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.id = (user as { id: string }).id;
        token.username = (user as { username?: string | null }).username;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        (session.user as { id?: string }).id = token.id as string;
        (session.user as { username?: string | null }).username = token.username as string | null | undefined;
      }
      return session;
    },
  },
  pages: { signIn: "/login" },
  secret: process.env.NEXTAUTH_SECRET,
};

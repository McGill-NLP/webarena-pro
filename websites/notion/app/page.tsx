import { isAuthed } from "@/lib/auth";
import { redirect } from "next/navigation";

export default function HomePage() {
  if (isAuthed()) {
    redirect("/app");
  }
  redirect("/login");
}

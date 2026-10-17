import { redirect } from "next/navigation";

/** The public site is the entry point; the operational console remains at /app. */
export default function Home() {
  redirect("/landing/index.html");
}

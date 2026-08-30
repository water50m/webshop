import { redirect } from "next/navigation";

/** Kept for old bookmarks; Page connection and selection now share /my-pages. */
export default function FacebookConnectionPage() {
  redirect("/my-pages");
}

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export default async function IndexPage() {
  const store = await cookies();
  redirect(store.has("ow_access") ? "/workspace" : "/login");
}

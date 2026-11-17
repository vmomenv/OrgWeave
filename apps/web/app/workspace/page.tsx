import type { Metadata } from "next";

import { Workspace } from "@/components/workspace/workspace";

export const metadata: Metadata = {
  title: "工作空间 — OrgWeave",
};

export default function WorkspacePage() {
  return <Workspace />;
}

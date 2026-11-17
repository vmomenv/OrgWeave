import type { Metadata, Viewport } from "next";

import { ThemeToggle } from "@/components/theme-toggle";

import "./globals.css";

const THEME_SCRIPT = `
try {
  var stored = localStorage.getItem("orgweave-theme");
  var dark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  if (dark) document.documentElement.classList.add("dark");
} catch (error) {}
`;

export const metadata: Metadata = {
  title: "OrgWeave — AI 组织操作系统",
  description:
    "以组织架构为基础、以 AI 员工为执行主体、以人类管理员为控制中心的多租户 AI 企业操作系统。",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8fafc" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1120" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-screen bg-background">
        <header className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/75">
          <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
            <div className="flex items-center gap-2.5">
              <span
                className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground"
                aria-hidden
              >
                OW
              </span>
              <div className="leading-tight">
                <p className="text-sm font-semibold tracking-tight">OrgWeave</p>
                <p className="text-[11px] text-muted-foreground">
                  AI Organization Operating System
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <a
                href="/workspace"
                className="hidden text-xs text-muted-foreground transition-colors hover:text-foreground sm:block"
              >
                工作空间
              </a>
              <a
                href="/status"
                className="hidden text-xs text-muted-foreground transition-colors hover:text-foreground sm:block"
              >
                系统状态
              </a>
              <span className="hidden text-xs text-muted-foreground md:block">
                Phase 1 · 组织与权限
              </span>
              <ThemeToggle />
            </div>
          </div>
        </header>
        {children}
        <footer className="mt-16 border-t">
          <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <span>OrgWeave · Phase 2 已验收 · 群聊与实时消息</span>
            <span className="font-mono">make infra · make api · make web · make workers</span>
          </div>
        </footer>
      </body>
    </html>
  );
}

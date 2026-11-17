"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { ArrowRight, Building2, Loader2, ShieldCheck, Users } from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Mode = "login" | "register";

export default function LoginPage() {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const endpoint = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const body =
        mode === "login"
          ? { email, password }
          : { email, password, display_name: displayName };
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        setError(payload?.error?.message ?? "请求失败，请稍后重试");
        return;
      }
      window.location.assign("/workspace");
    } catch {
      setError("无法连接服务器，请确认 API 已启动");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-[calc(100vh-3.5rem)] lg:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden flex-col justify-between border-r bg-muted/30 p-10 lg:flex">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
            OW
          </span>
          <div>
            <p className="text-base font-semibold tracking-tight">OrgWeave</p>
            <p className="text-xs text-muted-foreground">AI Organization Operating System</p>
          </div>
        </div>

        <div className="max-w-md space-y-6">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">
            让 AI 员工成为
            <br />
            组织中的真实成员
          </h1>
          <p className="text-sm leading-6 text-muted-foreground">
            多租户组织、独立身份、岗位与权限、独立 Session 与记忆、可观察可接管的
            Agent 协作平台。
          </p>
          <ul className="space-y-4 text-sm">
            <li className="flex items-start gap-3">
              <Building2 className="mt-0.5 h-4 w-4 text-primary" aria-hidden />
              <span>
                <span className="font-medium">真实组织架构</span>
                <span className="block text-xs text-muted-foreground">
                  部门、岗位、人类与 AI 员工统一建模
                </span>
              </span>
            </li>
            <li className="flex items-start gap-3">
              <Users className="mt-0.5 h-4 w-4 text-primary" aria-hidden />
              <span>
                <span className="font-medium">AI 团队协作</span>
                <span className="block text-xs text-muted-foreground">
                  任务委派、独立 Session、结果回传
                </span>
              </span>
            </li>
            <li className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 h-4 w-4 text-primary" aria-hidden />
              <span>
                <span className="font-medium">租户级隔离</span>
                <span className="block text-xs text-muted-foreground">
                  PostgreSQL RLS + 服务端租户上下文
                </span>
              </span>
            </li>
          </ul>
        </div>

        <p className="text-xs text-muted-foreground">
          Phase 1 · 用户、租户、组织架构与权限
        </p>
      </section>

      <section className="flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm space-y-6">
          <div className="flex items-center justify-between lg:hidden">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground">
                OW
              </span>
              <span className="text-sm font-semibold">OrgWeave</span>
            </div>
            <ThemeToggle />
          </div>

          <div className="space-y-1">
            <h2 className="text-2xl font-semibold tracking-tight">
              {mode === "login" ? "登录工作空间" : "创建账号"}
            </h2>
            <p className="text-sm text-muted-foreground">
              {mode === "login"
                ? "使用邮箱登录，进入你的企业租户。"
                : "注册后可创建企业或接受成员邀请。"}
            </p>
          </div>

          <div className="grid grid-cols-2 rounded-lg border bg-muted/40 p-1 text-sm">
            <button
              type="button"
              onClick={() => {
                setMode("login");
                setError(null);
              }}
              className={`rounded-md py-1.5 transition-colors ${
                mode === "login" ? "bg-background font-medium shadow-sm" : "text-muted-foreground"
              }`}
            >
              登录
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("register");
                setError(null);
              }}
              className={`rounded-md py-1.5 transition-colors ${
                mode === "register" ? "bg-background font-medium shadow-sm" : "text-muted-foreground"
              }`}
            >
              注册
            </button>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            {mode === "register" ? (
              <div className="space-y-1.5">
                <Label htmlFor="display-name">姓名</Label>
                <Input
                  id="display-name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="例如：张明"
                  required
                  maxLength={120}
                  autoComplete="name"
                />
              </div>
            ) : null}

            <div className="space-y-1.5">
              <Label htmlFor="email">邮箱</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@company.com"
                required
                autoComplete="email"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={mode === "register" ? "至少 10 位字符" : "输入密码"}
                required
                minLength={mode === "register" ? 10 : 1}
                autoComplete={mode === "register" ? "new-password" : "current-password"}
              />
            </div>

            {error ? (
              <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                {error}
              </p>
            ) : null}

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <ArrowRight className="mr-2 h-4 w-4" aria-hidden />
              )}
              {mode === "login" ? "登录" : "注册并登录"}
            </Button>
          </form>

          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <Link className="hover:text-foreground" href="/status">
              系统状态
            </Link>
            <span>会话存储在 httpOnly Cookie</span>
          </div>
        </div>
      </section>
    </div>
  );
}

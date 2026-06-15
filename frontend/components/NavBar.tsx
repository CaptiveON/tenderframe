"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function NavBar() {
  const { label, token, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const tab = (href: string, text: string) => (
    <Link
      href={href}
      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
        pathname === href
          ? "bg-slate-900 text-white"
          : "text-slate-600 hover:bg-slate-200"
      }`}
    >
      {text}
    </Link>
  );

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto max-w-6xl flex items-center gap-2 px-4 h-14">
        <Link href="/" className="font-semibold text-slate-900 mr-2">
          Tender<span className="text-emerald-600">Frame</span>
        </Link>
        {token && (
          <>
            {tab("/", "Chat")}
            {tab("/audits", "Audit log")}
          </>
        )}
        <div className="ml-auto flex items-center gap-3 text-sm">
          {token ? (
            <>
              <span className="text-slate-500">{label}</span>
              <button
                onClick={() => {
                  logout();
                  router.push("/login");
                }}
                className="text-slate-600 hover:text-slate-900"
              >
                Sign out
              </button>
            </>
          ) : (
            <Link href="/login" className="text-slate-600 hover:text-slate-900">
              Sign in
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}

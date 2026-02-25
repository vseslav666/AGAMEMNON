export default function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <main className="w-full max-w-xl rounded-3xl border border-white/20 bg-white/10 p-8 text-center shadow-[0_30px_80px_rgba(15,23,42,0.4)] backdrop-blur-2xl">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-50">TACACS Management UI</h1>
        <p className="mt-3 text-sm text-slate-200">
          Open the admin console to manage users, hosts, groups, and policies.
        </p>
        <a
          href="/admin"
          className="mt-6 inline-flex rounded-xl border border-cyan-200/40 bg-cyan-400/25 px-4 py-2 text-sm font-medium text-cyan-50 transition hover:bg-cyan-400/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/70"
        >
          Go to Admin
        </a>
      </main>
    </div>
  );
}

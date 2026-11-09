export function Header() {
  return (
    <header className="bg-ink text-white">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">GridMate</h1>
          <p className="text-sm text-white/70">From Weather to Watts, Intelligently</p>
        </div>
        <div className="text-right text-sm">
          <p className="font-medium">Lonavala, Maharashtra</p>
          <p className="rounded bg-white/10 px-2 py-0.5 text-xs text-amber-200">Simulation result: synthetic prototype data, not measured Lonavala data</p>
        </div>
      </div>
    </header>
  );
}

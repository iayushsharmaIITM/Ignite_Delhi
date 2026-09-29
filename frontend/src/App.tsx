export default function App() {
  return (
    <div className="flex h-full items-center justify-center bg-background">
      <div className="rounded-xl border border-border bg-card p-8 text-center shadow">
        <div className="mx-auto mb-4 h-12 w-12 rounded-xl bg-primary" />
        <h1 className="text-lg font-semibold text-foreground">Kestrel — new UI scaffold</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Step 1 complete: Vite + React + Tailwind + tokens. The chat shell lands next.
        </p>
      </div>
    </div>
  )
}

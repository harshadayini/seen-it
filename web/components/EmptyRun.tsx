/**
 * EmptyRun: shown on Results / Scene / Cart-adjacent screens when a backend is connected but
 * nothing has been scanned yet. Points the user to Scan instead of showing made-up items.
 */
import Link from "next/link";

/** @returns a short empty state with a link to the Scan screen. */
export function EmptyRun({ title = "Nothing scanned yet" }: { title?: string }) {
  return (
    <main id="main" className="screen">
      <header className="head">
        <span className="ghost" aria-hidden="true">scan</span>
        <h1 className="h1 over">{title}</h1>
        <p className="meta over">Paste a video or photo link and the real finds land here.</p>
      </header>
      <Link href="/" className="btn primary">Scan something</Link>
    </main>
  );
}

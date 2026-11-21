/**
 * Evidence: "How good is it?", opened from a small link in the top bar and not part of the main
 * flow. Three labelled regions: baseline vs ours, one failure and its cause, and how the labels
 * were made. Invariant: only real numbers belong here. Until eval/results exists every figure is a
 * clearly marked "[fill from eval/results]" placeholder; nothing is invented.
 */
import Link from "next/link";

/** A visibly unfilled slot. @param what what will go here */
function Placeholder({ what }: { what: string }) {
  return (
    <div className="ev-ph">
      <strong>[fill from eval/results]</strong>
      <span>{what}</span>
    </div>
  );
}

/** @returns the evidence page. */
export default function EvidencePage() {
  return (
    <main id="main" className="screen evidence">
      <header className="head">
        <h1 className="h1">How good is it?</h1>
        <p className="meta">Checked on videos we never tuned on, against a simple baseline. Numbers appear here only once they are measured.</p>
      </header>

      <section className="ev-card" aria-labelledby="ev-chart">
        <h2 id="ev-chart" className="panel-h">Baseline vs Seen It</h2>
        <p className="sub">The baseline looks at one middle frame, makes one guess and takes the top search result, with no checking.</p>
        <Placeholder what="Chart: baseline vs Seen It on held-out videos (items found, exact product, colour or variant, invented items)." />
      </section>

      <section className="ev-card" aria-labelledby="ev-fail">
        <h2 id="ev-fail" className="panel-h">One failure, and why</h2>
        <Placeholder what="One real failure from the held-out set: the item, what we returned, and the cause (for example motion blur, a look-alike product, or an item not in the catalog)." />
      </section>

      <section className="ev-card" aria-labelledby="ev-labels">
        <h2 id="ev-labels" className="panel-h">How the labels were made</h2>
        <p className="sub">The correct answers come from the product links in each creator&apos;s own video description, checked against the Shopify catalog. We did not write them.</p>
        <Placeholder what="Number of videos and products, and how many were held out." />
      </section>

      <Link href="/" className="link">Back to start</Link>
    </main>
  );
}

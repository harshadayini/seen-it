/**
 * Feature: one editorial section in the Sage layout, adapted to a phone.
 * Variant "pair": two tall photos, then text beside a small photo.
 * Variant "collage": text beside a wide photo, a huge faded word between the rows, then a
 * photo beside more text and a small pill link.
 * Boundary: presentational. Photos come from lib/assets.ts and fall back to labelled tiles.
 */
import Link from "next/link";
import { Asset } from "./Asset";
import type { AssetKey } from "@/lib/assets";

interface Common {
  title: string;
  text: string[];
}

interface Pair extends Common {
  variant: "pair";
  tall: [AssetKey, AssetKey];
  small: AssetKey;
}

interface Collage extends Common {
  variant: "collage";
  ghost: string;
  wide: AssetKey;
  low: AssetKey;
  cta: { label: string; href: string };
}

/** @returns the section for the given variant. */
export function Feature(props: Pair | Collage) {
  if (props.variant === "pair") {
    return (
      <section className="feat pair" aria-label={props.title}>
        <figure className="shot tall"><Asset name={props.tall[0]} className="fill" /></figure>
        <figure className="shot tall"><Asset name={props.tall[1]} className="fill" /></figure>
        <div className="feat-text">
          <h2>{props.title}</h2>
          {props.text.map((t) => <p key={t}>{t}</p>)}
        </div>
        <figure className="shot small"><Asset name={props.small} className="fill" /></figure>
      </section>
    );
  }
  return (
    <section className="feat collage" aria-label={props.title}>
      <div className="feat-text">
        <h2>{props.title}</h2>
        <p>{props.text[0]}</p>
      </div>
      <figure className="shot wide"><Asset name={props.wide} className="fill" /></figure>
      <span className="ghost big" aria-hidden="true">{props.ghost}</span>
      <figure className="shot low"><Asset name={props.low} className="fill" /></figure>
      <div className="feat-text end">
        {props.text.slice(1).map((t) => <p key={t}>{t}</p>)}
        <Link href={props.cta.href} className="btn outline small">{props.cta.label}</Link>
      </div>
    </section>
  );
}

/**
 * GET /api/run: serves fixtures/sample_run.json so the UI runs before the real
 * backend exists. Boundary: read-only stub; replaced by the FastAPI GET /run/<id>.
 * Invariant: never invents data; if the fixture is missing it returns a 500 error.
 */
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";

/** @returns the fixture run as JSON, or a structured error. */
export async function GET() {
  try {
    const file = path.join(process.cwd(), "..", "fixtures", "sample_run.json");
    return new Response(await fs.readFile(file, "utf8"), { headers: { "content-type": "application/json" } });
  } catch {
    return Response.json({ error: "fixture_unavailable" }, { status: 500 });
  }
}

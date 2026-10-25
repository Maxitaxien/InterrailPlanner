import { spawnSync, spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
const root = resolve(import.meta.dirname, "..");
const temp = mkdtempSync(join(tmpdir(), "interrail-e2e-"));
const python = process.env.TEST_PYTHON || resolve(root, "../.venv/bin/python");
// Test-only empty SearXNG fixture: never contact real search engines in browser tests.
const search = createServer((request, response) => {
  response.writeHead(request.url.startsWith("/search?") ? 200 : 404, { "Content-Type": "application/json" });
  response.end(JSON.stringify({ results: [] }));
});
await new Promise(resolve => search.listen(0, "127.0.0.1", resolve));
const env = { ...process.env, DATABASE_URL: `sqlite:///${temp}/test.db`, OLLAMA_BASE_URL: "http://127.0.0.1:1", LLM_TIMEOUT_SECONDS: "1", SEARXNG_BASE_URL: `http://127.0.0.1:${search.address().port}` };
const options = { cwd: resolve(root, "../backend"), env, stdio: "inherit" };
for (const args of [["-m", "alembic", "upgrade", "head"], ["-m", "app.scripts.seed_data"]]) {
  const result = spawnSync(python, args, options);
  if (result.status !== 0) { rmSync(temp, { recursive: true, force: true }); process.exit(result.status || 1); }
}
const child = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], options);
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
child.on("exit", code => { search.close(); rmSync(temp, { recursive: true, force: true }); process.exit(code || 0); });

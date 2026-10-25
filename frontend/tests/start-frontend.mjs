import { cpSync } from "node:fs";
import { spawn } from "node:child_process";
import { resolve } from "node:path";
const root = resolve(import.meta.dirname, "..");
cpSync(resolve(root, ".next/static"), resolve(root, ".next/standalone/.next/static"), { recursive: true });
const child = spawn(process.execPath, [resolve(root, ".next/standalone/server.js")], {
  cwd: root, stdio: "inherit", env: { ...process.env, HOSTNAME: "127.0.0.1", PORT: "3000", API_INTERNAL_URL: "http://127.0.0.1:8000" },
});
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
child.on("exit", code => process.exit(code || 0));

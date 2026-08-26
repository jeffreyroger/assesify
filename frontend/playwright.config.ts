import { defineConfig, devices } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

/**
 * Playwright E2E config (spec §10).
 *
 * Kept deliberately separate from `npm test` (Vitest): the unit suite stays
 * fast and hermetic, this one drives both real servers.
 *
 * Both servers run against a *throwaway* SQLite database under
 * `backend/instance/e2e.db` - never `backend/assesify_dev.db`.
 */
const BACKEND_DIR = path.resolve(__dirname, "..", "backend");
const PY = path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe");
const PY_POSIX = path.join(BACKEND_DIR, ".venv", "bin", "python");
const PYTHON = existsSync(PY) ? PY : PY_POSIX;

const DB_FILE = path.join(BACKEND_DIR, "instance", "e2e.db");
const DATABASE_URL = `sqlite:///${DB_FILE.split(path.sep).join("/")}`;

const BACKEND_PORT = 5101;
const FRONTEND_PORT = 3101;
const API_BASE_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const BASE_URL = `http://127.0.0.1:${FRONTEND_PORT}`;

// Read back by the API-level E2E test.
process.env.PW_API_BASE_URL = API_BASE_URL;

const backendEnv = {
  ...process.env,
  DATABASE_URL,
  FLASK_APP: "app.main:app",
  // The backend only reflects CORS headers for exactly this origin
  // (`app/main.py::add_cors_headers`), which defaults to localhost:3000.
  FRONTEND_URL: BASE_URL,
  JWT_SECRET_KEY: "e2e-jwt-secret",
};

// Seed synchronously while the config is still being evaluated, so the fixture
// data exists before either server (or globalSetup) starts.
if (!process.env.PW_SKIP_SEED) {
  // Best effort: a server left running from a previous run (reuseExistingServer)
  // holds the file open on Windows. The seed always creates a *new* lesson and
  // quiz and reports their ids, so an existing file is harmless.
  try {
    rmSync(DB_FILE, { force: true });
  } catch {
    /* keep the existing database */
  }
  const out = execFileSync(PYTHON, ["e2e_seed.py"], {
    cwd: BACKEND_DIR,
    env: backendEnv,
    encoding: "utf8",
  });
  const seeded = JSON.parse(out.trim().split("\n").pop() as string);
  writeFileSync(path.join(__dirname, "e2e", ".seed.json"), JSON.stringify(seeded, null, 2));
}

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${PYTHON}" -m flask run --port ${BACKEND_PORT} --host 127.0.0.1`,
      cwd: BACKEND_DIR,
      url: `${API_BASE_URL}/metrics`,
      env: backendEnv,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      // `NEXT_PUBLIC_*` values are inlined at build time and are *not* part
      // of Next's build-cache key, so a stale `.next` from a normal
      // `npm run build` would bake in the default API base URL and every
      // request from the page would fail. Clear it first.
      command: `node -e "require('fs').rmSync('.next',{recursive:true,force:true})" && npm run build && npm run start -- --port ${FRONTEND_PORT}`,
      cwd: __dirname,
      url: BASE_URL,
      env: { ...process.env, NEXT_PUBLIC_API_BASE_URL: API_BASE_URL },
      reuseExistingServer: !process.env.CI,
      timeout: 300_000,
    },
  ],
});

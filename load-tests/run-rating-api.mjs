import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const defaults = {
  BASE_URL: "https://universityapp.site",
  TARGET_RPS: "500",
  DURATION: "2m",
  ZACH_NUMBERS: "247168",
};

const aliases = {
  "--base-url": "BASE_URL",
  "--rps": "TARGET_RPS",
  "--duration": "DURATION",
  "--zach": "ZACH_NUMBERS",
  "--zach-numbers": "ZACH_NUMBERS",
  "--pre-vus": "PRE_ALLOCATED_VUS",
  "--max-vus": "MAX_VUS",
  "--p95-ms": "P95_MS",
  "--error-rate": "ERROR_RATE",
};

const env = { ...process.env, ...defaults };
const passthrough = [];

for (const arg of process.argv.slice(2)) {
  if (arg === "--help" || arg === "-h") {
    printHelp();
    process.exit(0);
  }

  const [rawName, rawValue] = arg.split("=", 2);
  const key = aliases[rawName];

  if (!key || rawValue === undefined) {
    passthrough.push(arg);
    continue;
  }

  env[key] = rawValue;
}

const result = spawnSync("k6", ["run", "load-tests/rating-api.js", ...passthrough], {
  cwd: fileURLToPath(new URL("..", import.meta.url)),
  env,
  stdio: "inherit",
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 1);

function printHelp() {
  console.log(`Usage:
  node load-tests/run-rating-api.mjs --rps=500 --duration=2m --zach=247168
  node load-tests/run-rating-api.mjs --rps=1500 --duration=1m --zach=247168 --pre-vus=750 --max-vus=3000

Options:
  --base-url=https://universityapp.site
  --rps=500
  --duration=2m
  --zach=247168,247169
  --pre-vus=750
  --max-vus=3000
  --p95-ms=300
  --error-rate=0.01
`);
}

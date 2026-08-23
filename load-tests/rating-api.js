import http from "k6/http";
import { check } from "k6";
import exec from "k6/execution";
import { Rate } from "k6/metrics";

const BASE_URL = (__ENV.BASE_URL || "https://universityapp.site").replace(/\/+$/, "");
const TARGET_RPS = Number(__ENV.TARGET_RPS || "500");
const DURATION = __ENV.DURATION || "2m";
const ZACH_NUMBERS = (__ENV.ZACH_NUMBERS || "247168")
  .split(",")
  .map((item) => item.trim())
  .filter(Boolean);
const PRE_ALLOCATED_VUS = Number(__ENV.PRE_ALLOCATED_VUS || Math.max(100, Math.ceil(TARGET_RPS / 2)));
const MAX_VUS = Number(__ENV.MAX_VUS || Math.max(PRE_ALLOCATED_VUS * 2, TARGET_RPS * 2));
const P95_MS = Number(__ENV.P95_MS || "300");
const ERROR_RATE = Number(__ENV.ERROR_RATE || "0.01");

const apiSuccess = new Rate("api_success");

const endpoints = [
  { name: "student_group", path: "/students/{zach}/group" },
  { name: "zachet", path: "/rating/{zach}/zachet" },
  { name: "ekzamen", path: "/rating/{zach}/ekzamen" },
  { name: "vypusknaya_rabota", path: "/rating/{zach}/vypusknaya-rabota" },
  { name: "gosekzamen", path: "/rating/{zach}/gosekzamen" },
  { name: "kontrolnaya_rabota", path: "/rating/{zach}/kontrolnaya-rabota" },
  { name: "kursovaya_rabota", path: "/rating/{zach}/kursovaya-rabota" },
  { name: "kursovoy_proekt", path: "/rating/{zach}/kursovoy-proekt" },
  { name: "praktika", path: "/rating/{zach}/praktika" },
];

export const options = {
  discardResponseBodies: true,
  scenarios: {
    api_rps: {
      executor: "constant-arrival-rate",
      rate: TARGET_RPS,
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: PRE_ALLOCATED_VUS,
      maxVUs: MAX_VUS,
    },
  },
  thresholds: {
    api_success: [`rate>${1 - ERROR_RATE}`],
    http_req_failed: [`rate<${ERROR_RATE}`],
    http_req_duration: [`p(95)<${P95_MS}`],
    dropped_iterations: ["count==0"],
  },
};

export function setup() {
  if (!Number.isFinite(TARGET_RPS) || TARGET_RPS <= 0) {
    throw new Error("TARGET_RPS must be a positive number");
  }
  if (!ZACH_NUMBERS.length) {
    throw new Error("ZACH_NUMBERS must contain at least one zach number");
  }
}

export default function () {
  const iteration = exec.scenario.iterationInTest;
  const endpoint = endpoints[iteration % endpoints.length];
  const zach = ZACH_NUMBERS[Math.floor(iteration / endpoints.length) % ZACH_NUMBERS.length];
  const url = `${BASE_URL}${endpoint.path.replace("{zach}", encodeURIComponent(zach))}`;

  const response = http.get(url, {
    tags: {
      endpoint: endpoint.name,
    },
    timeout: "10s",
  });

  const ok = check(response, {
    "status is 200": (res) => res.status === 200,
  });

  apiSuccess.add(ok);
}

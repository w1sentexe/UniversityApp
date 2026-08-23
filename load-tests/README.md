# Rating API load test

The scenario sends read-only API requests to production by default:

```bash
node load-tests/run-rating-api.mjs --rps=500 --duration=2m --zach=247168
```

Higher pressure run:

```bash
node load-tests/run-rating-api.mjs --rps=1500 --duration=1m --zach=247168 --pre-vus=750 --max-vus=3000
```

The k6 scenario uses `constant-arrival-rate`, so one iteration equals one API
request. `--rps=1500` means 1500 HTTP requests per second, not 1500 virtual
users.

Useful options:

```bash
node load-tests/run-rating-api.mjs \
  --base-url=https://universityapp.site \
  --rps=500 \
  --duration=2m \
  --zach=247168,247169 \
  --p95-ms=300 \
  --error-rate=0.01
```

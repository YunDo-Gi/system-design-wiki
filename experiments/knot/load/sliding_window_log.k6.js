// experiments/knot/load/sliding_window_log.k6.js
// shorten 엔드포인트 (분당 10) — 4 시나리오:
// burst, ramp, steady_burst_cycle, boundary_burst_replay (cycle 2와 동일 패턴으로 비교)

import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:8001';

export const options = {
  scenarios: {
    burst: {
      executor: 'per-vu-iterations',
      vus: 20,
      iterations: 1,
      maxDuration: '5s',
      startTime: '0s',
      tags: { scenario: 'burst' },
    },
    ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      stages: [{ duration: '60s', target: 30 }],
      preAllocatedVUs: 30,
      maxVUs: 100,
      timeUnit: '1s',
      startTime: '10s',
      tags: { scenario: 'ramp' },
    },
    steady_burst_cycle: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      stages: [
        { duration: '1s', target: 20 }, { duration: '5s', target: 0 },
        { duration: '1s', target: 20 }, { duration: '5s', target: 0 },
        { duration: '1s', target: 20 }, { duration: '5s', target: 0 },
      ],
      preAllocatedVUs: 30,
      maxVUs: 50,
      timeUnit: '1s',
      startTime: '80s',
      tags: { scenario: 'steady_burst_cycle' },
    },
    boundary_burst_replay: {
      // cycle 2 fixed_window와 동일 시나리오. sliding window는 spike-deny-spike 패턴이 아닌 균등 throttle 보여야 함
      executor: 'constant-arrival-rate',
      rate: 30,
      timeUnit: '1s',
      duration: '12s',
      preAllocatedVUs: 20,
      maxVUs: 50,
      startTime: '120s',
      tags: { scenario: 'boundary_burst_replay' },
    },
  },
};

export default function () {
  const res = http.post(`${BASE_URL}/shorten`, JSON.stringify({ url: 'https://example.com' }), {
    headers: { 'content-type': 'application/json', 'x-api-key': `k6-${__VU}` },
  });
  check(res, { 'status is 200 or 429': (r) => r.status === 200 || r.status === 429 });
}

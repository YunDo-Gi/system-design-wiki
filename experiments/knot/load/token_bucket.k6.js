// experiments/knot/load/token_bucket.k6.js
import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:8000';
const CODE = __ENV.CODE;  // 사전 단축 코드 (외부에서 주입)

export const options = {
  scenarios: {
    burst: {
      executor: 'per-vu-iterations',
      vus: 200,
      iterations: 1,
      maxDuration: '5s',
      startTime: '0s',
      tags: { scenario: 'burst' },
    },
    ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      stages: [
        { duration: '60s', target: 100 },
      ],
      preAllocatedVUs: 50,
      maxVUs: 200,
      timeUnit: '1s',
      startTime: '10s',
      tags: { scenario: 'ramp' },
    },
    steady_burst_cycle: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      stages: [
        { duration: '1s', target: 100 }, { duration: '5s', target: 0 },
        { duration: '1s', target: 100 }, { duration: '5s', target: 0 },
        { duration: '1s', target: 100 }, { duration: '5s', target: 0 },
      ],
      preAllocatedVUs: 100,
      maxVUs: 200,
      timeUnit: '1s',
      startTime: '80s',
      tags: { scenario: 'steady_burst_cycle' },
    },
  },
  thresholds: {
    'http_reqs{status:429}': ['count>0'],  // 거부가 일어나야 token bucket 검증 의미
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/${CODE}`, { redirects: 0 });
  check(res, {
    'status is 302 or 429': (r) => r.status === 302 || r.status === 429,
  });
}

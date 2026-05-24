// experiments/knot/load/fixed_window_boundary.k6.js
// 시나리오: 12초간 200rps 지속. 분 경계가 그 중간에 떨어지면 통과·거부 패턴이
// "burst pass → all deny → burst pass" 형태로 차트에 박힘.

import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:8001';
const CODE = __ENV.CODE;

export const options = {
  scenarios: {
    boundary_burst: {
      executor: 'constant-arrival-rate',
      rate: 200,            // 200 req/s
      timeUnit: '1s',
      duration: '12s',
      preAllocatedVUs: 100,
      maxVUs: 300,
      tags: { scenario: 'boundary_burst' },
    },
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/${CODE}`, { redirects: 0 });
  check(res, { 'status is 302 or 429': (r) => r.status === 302 || r.status === 429 });
}

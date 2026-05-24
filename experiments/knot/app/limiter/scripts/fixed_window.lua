-- experiments/knot/app/limiter/scripts/fixed_window.lua
-- KEYS[1] = base key prefix (knot:fw:endpoint:identity)
-- ARGV[1] = limit (int), ARGV[2] = window_size_seconds (int)
-- returns: {allowed (0|1), limit, remaining, retry_after_ms, window_start}

local now_pair = redis.call('TIME')
local now = tonumber(now_pair[1])
local window_size = tonumber(ARGV[2])
local window_start = math.floor(now / window_size) * window_size

local key = KEYS[1] .. ':' .. window_start
local count = redis.call('INCR', key)

if count == 1 then
  redis.call('EXPIRE', key, window_size + 5)
end

local limit = tonumber(ARGV[1])
local allowed = 0
local remaining = 0
local retry_after_ms = 0

if count <= limit then
  allowed = 1
  remaining = limit - count
else
  remaining = 0
  retry_after_ms = (window_start + window_size - now) * 1000
end

return {allowed, limit, remaining, retry_after_ms, window_start}

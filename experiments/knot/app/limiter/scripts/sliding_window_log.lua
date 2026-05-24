-- experiments/knot/app/limiter/scripts/sliding_window_log.lua
-- KEYS[1] = ZSET key
-- ARGV[1] = limit, ARGV[2] = window_size_seconds, ARGV[3] = random_hex_4
-- returns: {allowed (0|1), limit, remaining, retry_after_ms}

local now_pair = redis.call('TIME')
local now_us = tonumber(now_pair[1]) * 1000000 + tonumber(now_pair[2])

local window_size = tonumber(ARGV[2])
local window_us = window_size * 1000000
local cutoff = now_us - window_us

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, cutoff)
local count = redis.call('ZCARD', KEYS[1])
local limit = tonumber(ARGV[1])

local allowed = 0
local remaining = 0
local retry_after_ms = 0

if count < limit then
  local member = tostring(now_us) .. '-' .. ARGV[3]
  redis.call('ZADD', KEYS[1], now_us, member)
  allowed = 1
  remaining = limit - count - 1
else
  remaining = 0
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  if #oldest >= 2 then
    local oldest_us = tonumber(oldest[2])
    retry_after_ms = math.ceil((oldest_us + window_us - now_us) / 1000)
  end
end

redis.call('EXPIRE', KEYS[1], window_size + 5)

return {allowed, limit, remaining, retry_after_ms}

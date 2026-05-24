-- KEYS[1] = bucket key
-- ARGV[1] = capacity (int), ARGV[2] = refill_rate (tokens/sec, float), ARGV[3] = cost (int)
-- returns: {allowed (0|1), remaining (int floor), retry_after_ms (int)}

local now_pair = redis.call('TIME')
local now = tonumber(now_pair[1]) + tonumber(now_pair[2]) / 1e6

local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

local data = redis.call('HMGET', KEYS[1], 'tokens', 'last_refill')
local tokens = tonumber(data[1]) or capacity
local last = tonumber(data[2]) or now

local elapsed = math.max(0, now - last)
tokens = math.min(capacity, tokens + elapsed * rate)

local allowed = 0
local retry_after = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry_after = math.ceil((cost - tokens) / rate * 1000)
end

redis.call('HMSET', KEYS[1], 'tokens', tokens, 'last_refill', now)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / rate * 2))

return {allowed, math.floor(tokens), retry_after}

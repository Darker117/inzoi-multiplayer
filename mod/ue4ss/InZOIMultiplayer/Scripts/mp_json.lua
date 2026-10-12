-- Minimal JSON for the messages between the game and the inZOI Multiplayer program (objects, arrays, strings,
-- numbers, true/false/null). null decodes to nil inside objects and to json.null inside arrays.
local json = { null = setmetatable({}, { __tostring = function() return "null" end }) }

local escapes = { ['"'] = '\\"', ["\\"] = "\\\\", ["\b"] = "\\b", ["\f"] = "\\f", ["\n"] = "\\n", ["\r"] = "\\r", ["\t"] = "\\t" }

local function encode_string(s)
  return '"' .. s:gsub('[%c"\\]', function(c) return escapes[c] or string.format("\\u%04x", c:byte()) end) .. '"'
end

local function is_array(t)
  local n = 0
  for k in pairs(t) do
    if type(k) ~= "number" or k < 1 or k % 1 ~= 0 then return false end
    n = n + 1
  end
  for i = 1, n do if t[i] == nil then return false end end
  return true
end

function json.encode(v)
  local t = type(v)
  if v == nil or v == json.null then return "null" end
  if t == "boolean" then return v and "true" or "false" end
  if t == "number" then
    if v ~= v or v == math.huge or v == -math.huge then return "null" end
    if v % 1 == 0 and math.abs(v) < 1e15 then return string.format("%d", v) end
    return string.format("%.14g", v)
  end
  if t == "string" then return encode_string(v) end
  if t == "table" then
    local parts = {}
    if next(v) == nil then return "{}" end
    if is_array(v) then
      for i = 1, #v do parts[i] = json.encode(v[i]) end
      return "[" .. table.concat(parts, ",") .. "]"
    end
    for k, x in pairs(v) do parts[#parts + 1] = encode_string(tostring(k)) .. ":" .. json.encode(x) end
    return "{" .. table.concat(parts, ",") .. "}"
  end
  error("can't encode " .. t)
end

local function utf8char(c)
  if c < 0x80 then return string.char(c) end
  if c < 0x800 then return string.char(0xC0 + (c >> 6), 0x80 + (c & 0x3F)) end
  if c < 0x10000 then return string.char(0xE0 + (c >> 12), 0x80 + ((c >> 6) & 0x3F), 0x80 + (c & 0x3F)) end
  return string.char(0xF0 + (c >> 18), 0x80 + ((c >> 12) & 0x3F), 0x80 + ((c >> 6) & 0x3F), 0x80 + (c & 0x3F))
end

function json.decode(s)
  local i = 1
  local function err(what) error("json: " .. what .. " at " .. i) end
  local function ws() i = s:find("[^ \t\r\n]", i) or #s + 1 end
  local value
  local function str()
    i = i + 1
    local out = {}
    while true do
      local j = s:find('["\\]', i)
      if not j then err("unterminated string") end
      out[#out + 1] = s:sub(i, j - 1)
      if s:sub(j, j) == '"' then i = j + 1; break end
      local e = s:sub(j + 1, j + 1)
      local map = { b = "\b", f = "\f", n = "\n", r = "\r", t = "\t", ['"'] = '"', ["\\"] = "\\", ["/"] = "/" }
      if map[e] then out[#out + 1] = map[e]; i = j + 2
      elseif e == "u" then
        local c = tonumber(s:sub(j + 2, j + 5), 16) or err("bad \\u")
        i = j + 6
        if c >= 0xD800 and c <= 0xDBFF and s:sub(i, i + 1) == "\\u" then
          local lo = tonumber(s:sub(i + 2, i + 5), 16)
          if lo and lo >= 0xDC00 and lo <= 0xDFFF then c = 0x10000 + ((c - 0xD800) << 10) + (lo - 0xDC00); i = i + 6 end
        end
        out[#out + 1] = utf8char(c)
      else err("bad escape") end
    end
    return table.concat(out)
  end
  function value()
    ws()
    local c = s:sub(i, i)
    if c == "{" then
      i = i + 1
      local t = {}
      ws()
      if s:sub(i, i) == "}" then i = i + 1; return t end
      while true do
        ws()
        if s:sub(i, i) ~= '"' then err("expected key") end
        local k = str()
        ws()
        if s:sub(i, i) ~= ":" then err("expected :") end
        i = i + 1
        local v = value()
        if v ~= json.null then t[k] = v end
        ws()
        local d = s:sub(i, i)
        i = i + 1
        if d == "}" then return t end
        if d ~= "," then err("expected , or }") end
      end
    elseif c == "[" then
      i = i + 1
      local t = {}
      ws()
      if s:sub(i, i) == "]" then i = i + 1; return t end
      while true do
        t[#t + 1] = value()
        ws()
        local d = s:sub(i, i)
        i = i + 1
        if d == "]" then return t end
        if d ~= "," then err("expected , or ]") end
      end
    elseif c == '"' then return str()
    elseif s:sub(i, i + 3) == "true" then i = i + 4; return true
    elseif s:sub(i, i + 4) == "false" then i = i + 5; return false
    elseif s:sub(i, i + 3) == "null" then i = i + 4; return json.null
    else
      local num = s:match("^-?%d+%.?%d*[eE]?[-+]?%d*", i)
      if not num or num == "" then err("unexpected '" .. c .. "'") end
      i = i + #num
      return tonumber(num)
    end
  end
  local ok, v = pcall(value)
  if not ok then return nil, v end
  return v
end

return json

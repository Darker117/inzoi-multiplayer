-- inZOI Multiplayer - B1 (client) side. Bound to the player's family Zois only to receive the B2 puppet controller's
-- reports (inzoi.message.send_to_client) and hand them to the companion app: each report is saved with the game's
-- uimod.cfg_save into <mod>/out/m<slot>.cfg, which the companion reads.
--   content = "<instance> <n> <kind> <text>"   (n counts up per controller instance; 32 slots are reused)
local M = {}
local MOD = "InZOIMultiplayer"

---@param self table
---@param owner AB1Character
---@param msgType string
---@param content string
function M.on_lua_message(self, owner, msgType, content)
    if tostring(msgType) ~= "mp" then return end
    content = tostring(content)
    local n = tonumber(content:match("^%S+ (%d+) ")) or 0
    inzoi.cli.execute(string.format('uimod.cfg_save mod_id=%s section=out key=m%d value="%s"', MOD, n % 32,
        (content:gsub('"', "'"))))
end

return M

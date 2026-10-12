-- Dialogs on the Multiplayer page, made of the game's own popup parts: the standard popup (WBP_Common_PopUp: dimmed
-- backdrop, rounded panel, title, text, popup buttons), text boxes and their labels from the game's code-entry popup
-- (WBP_Common_KCNInputPopup) and the game's toggle switch.
--
-- The program describes the dialog in page.json ("dialog": {id, title, desc, error, fields, toggles, buttons});
-- a button sends {t: "dialog", button, fields: {id: text}, toggles: {id: on}}.
local U = require("mp_util")
local D = {}

local POPUP = "/Game/UI/Common/Components/WBP_Common_PopUp.WBP_Common_PopUp_C"
local POPUP_BUTTON = "/Game/UI/Common/Components/WBP_Common_Button_Popup.WBP_Common_Button_Popup_C"
local INPUT_POPUP = "/Game/UI/Common/Components/WBP_Common_KCNInputPopup.WBP_Common_KCNInputPopup_C"
local TOGGLE = "/Game/UI/Common/Components/Toggle/WBP_Common_ToggleSwitch.WBP_Common_ToggleSwitch_C"
local BUTTON_TYPE = { fill = 1, line = 3 }            -- EB1ButtonType: PrimaryPositive, Secondary

local WBL
local function class(path)
  local c = StaticFindObject(path)
  if not U.valid(c) and LoadAsset then pcall(LoadAsset, path); c = StaticFindObject(path) end
  return c
end

local function create(path, owner)
  WBL = WBL or StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
  local c = class(path)
  if not U.valid(c) then error("missing " .. path) end
  return WBL:Create(owner, c, owner:GetOwningPlayer())
end

local function slot_of(widget)
  local s = widget.Slot
  local p = s.Padding
  local out = { pad = { Left = p.Left, Top = p.Top, Right = p.Right, Bottom = p.Bottom } }
  pcall(function() out.size = { SizeRule = s.Size.SizeRule, Value = s.Size.Value } end)
  pcall(function() out.h, out.v = s.HorizontalAlignment, s.VerticalAlignment end)
  return out
end

local function add_v(box, w, pad, h)
  local slot = box:AddChildToVerticalBox(w)
  if pad then slot:SetPadding(pad) end
  if h then slot:SetHorizontalAlignment(h) end
  return slot
end

-- Insert our rows into the popup's column right after its text (a VerticalBox can only append: take the rest out
-- and put it back after).
local function insert_rows(column, after, rows)
  local idx = column:GetChildIndex(after)
  local tail = {}
  for i = column:GetChildrenCount() - 1, idx + 1, -1 do
    local c = column:GetChildAt(i)
    table.insert(tail, 1, { w = c, s = slot_of(c) })
    column:RemoveChildAt(i)
  end
  for _, r in ipairs(rows) do add_v(column, r.w, r.pad, r.h) end
  for _, t in ipairs(tail) do
    local slot = column:AddChildToVerticalBox(t.w)
    slot:SetPadding(t.s.pad)
    if t.s.size then slot:SetSize(t.s.size) end
    if t.s.h then slot:SetHorizontalAlignment(t.s.h); slot:SetVerticalAlignment(t.s.v) end
  end
end

-- A text box with its label, taken out of a fresh copy of the game's code-entry popup.
local function input_row(popup, f)
  local donor = create(INPUT_POPUP, popup)
  local label = U.find(donor, "B1TextBlock_30")
  local box = U.part(donor, "BW_EditableTextBox_KCNCode")
  label:RemoveFromParent()
  box:RemoveFromParent()
  U.text(label, f.label or "")
  box:SetText(FText(f.value or ""))
  pcall(function() box:SetHintText(FText(f.hint or "")) end)
  if f.secret then pcall(function() box:SetIsPassword(true) end) end
  U.show(label, "hit")
  U.show(box, true)
  return label, box
end

local function toggle_row(popup, t)
  local donor = create(INPUT_POPUP, popup)
  local label = U.find(donor, "B1TextBlock_30")
  label:RemoveFromParent()
  U.text(label, t.label or "")
  U.show(label, "hit")
  local row = StaticConstructObject(StaticFindObject("/Script/BlueUMG.B1HorizontalBox"), popup.WidgetTree,
                                    FName("MP_Toggle_" .. tostring(t.id)))
  local sw = create(TOGGLE, popup)
  local s1 = row:AddChildToHorizontalBox(sw)
  s1:SetVerticalAlignment(2)
  local s2 = row:AddChildToHorizontalBox(label)
  s2:SetVerticalAlignment(2)
  s2:SetPadding({ Left = 12, Top = 0, Right = 0, Bottom = 0 })
  local switch = U.part(sw, "BW_WidgetSwitcher_InteractionToggle")
  if U.valid(switch) then switch:SetActiveWidgetIndex(t.on and 1 or 0) end
  return row, switch
end

local function close()
  local d = MP.dlg
  MP.dlg = nil
  if d and U.valid(d.w) then
    for _, b in ipairs(d.buttons or {}) do U.drop_handlers(b.BW_Button) end
    d.w:RemoveFromParent()
  end
end

local function answer(button)
  local d = MP.dlg
  if not d then return end
  local fields, toggles = {}, {}
  for _, f in ipairs(d.fields) do
    local ok, v = pcall(function() return f.box:GetText():ToString() end)
    fields[f.id] = ok and v or ""
  end
  for _, t in ipairs(d.toggles) do
    local ok, on = pcall(function() return t.switch:GetActiveWidgetIndex() == 1 end)
    toggles[t.id] = ok and on or false
    fields[t.id] = toggles[t.id]
  end
  U.send({ t = "dialog", button = button, fields = fields, toggles = toggles })
  close()                                                    -- the program puts it back if it has more to say
end

local function desc_text(dialog)
  local s = dialog.desc or ""
  if dialog.error and dialog.error ~= "" then s = (s ~= "" and (s .. "\n\n") or "") .. "⚠ " .. dialog.error end
  return s
end

function D.render(page, dialog)
  if not dialog then
    if MP.dlg then close() end
    return
  end
  local key = tostring(dialog.id) .. "|" .. tostring(dialog.title) .. "|" .. tostring(dialog.rev or "")
  local d = MP.dlg
  if d and d.key == key and U.valid(d.w) then
    U.text(d.desc, desc_text(dialog))
    return
  end
  close()
  local popup = create(POPUP, page)
  local root = page.WidgetTree.RootWidget
  local slot = root:AddChildToOverlay(popup)
  slot:SetHorizontalAlignment(0)
  slot:SetVerticalAlignment(0)
  d = { key = key, w = popup, fields = {}, toggles = {}, buttons = {} }
  MP.dlg = d
  U.show(U.part(popup, "BW_Button_Optional_Close"), false)
  U.show(U.part(popup, "BW_CheckBox_NeverShow"), false)
  U.show(U.part(popup, "BW_HorizontalBox_Timer"), false)
  local title = U.part(popup, "BW_RichText_Title")
  title:SetText(FText(dialog.title or ""))
  U.show(title, "hit")
  d.desc = U.part(popup, "BW_RichText_Desc")
  U.text(d.desc, desc_text(dialog))
  -- our fields, under the text
  local rows = {}
  for _, f in ipairs(dialog.fields or {}) do
    local label, box = input_row(popup, f)
    rows[#rows + 1] = { w = label, pad = { Left = 0, Top = 14, Right = 40, Bottom = 4 } }
    rows[#rows + 1] = { w = box, pad = { Left = 0, Top = 0, Right = 40, Bottom = 0 } }
    d.fields[#d.fields + 1] = { id = f.id, box = box }
  end
  for _, t in ipairs(dialog.toggles or {}) do
    local row, switch = toggle_row(popup, t)
    rows[#rows + 1] = { w = row, pad = { Left = 0, Top = 16, Right = 40, Bottom = 0 } }
    d.toggles[#d.toggles + 1] = { id = t.id, switch = switch }
  end
  if #rows > 0 then
    local column = U.part(popup, "B1VerticalBox_0")
    local after = U.part(popup, "B1SizeBox_0")
    insert_rows(column, after, rows)
  end
  -- the buttons
  local bar = U.part(popup, "BW_HorizontalBox_Button")
  for i = 0, bar:GetChildrenCount() - 1 do U.show(bar:GetChildAt(i), false) end
  for _, b in ipairs(dialog.buttons or { { id = "close", text = "OK", style = "fill" } }) do
    local w = create(POPUP_BUTTON, popup)
    pcall(function() w.ButtonType = BUTTON_TYPE[b.style or "line"] or 3 end)
    local s = bar:AddChildToHorizontalBox(w)
    s:SetPadding({ Left = 8, Top = 0, Right = 0, Bottom = 0 })
    U.text(w.BW_Text, b.text or b.id)
    U.show(w.BW_Image_Icon, false, U.COLLAPSED)
    U.show(w, true)
    local id = b.id
    U.on_click(w.BW_Button, function() answer(id) end)
    d.buttons[#d.buttons + 1] = w
  end
  if d.fields[1] then pcall(function() d.fields[1].box:SetKeyboardFocus() end) end
end

function D.close() close() end

return D

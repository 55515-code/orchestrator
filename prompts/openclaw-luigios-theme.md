# OpenClaw Theme Generation Prompt — LuigiOS "CachyOS COSMIC Workstation"

## Role
You are generating a complete, production-ready OpenClaw theme based on the **LuigiOS** design system (CachyOS COSMIC Developer Workstation variant). Output must cover **all three OpenClaw theme surfaces**: TUI terminal, Control UI web dashboard, and Dashboard third-party skin.

---

## 1. Canonical LuigiOS Color Tokens (Source of Truth)

These values are non-negotiable. Map them exactly.

| Token | Hex | RGB | Usage in LuigiOS |
|---|---|---|---|
| `accent_primary` | `#22C55E` | `rgb(34, 197, 94)` | Focus, selection, progress, buttons, git added |
| `accent_bright` | `#66FF66` | `rgb(102, 255, 102)` | Cursor, bright green, hover states, headings |
| `accent_deep` | `#00B14B` | `rgb(0, 177, 75)` | Deep green variant |
| `surface_950` | `#000000` | `rgb(0, 0, 0)` | OLED black, editor backgrounds |
| `surface_900` | `#121416` | `rgb(18, 20, 22)` | Sidebar, status bar, terminal background |
| `surface_800` | `#1A1A1A` | `rgb(26, 26, 26)` | Dropdowns, input fields, containers |
| `surface_700` | `#262626` | `rgb(38, 38, 38)` | Borders, inactive tabs, secondary buttons |
| `text_primary` | `#F5F7FA` | `rgb(245, 247, 250)` | Main text, active titles |
| `text_secondary` | `#C9D1D9` | `rgb(201, 209, 217)` | Body text, icons, terminal foreground |
| `text_muted` | `#9CA3AF` | `rgb(156, 163, 175)` | Inactive text, line numbers |
| `state_warning` | `#FBBF24` | `rgb(251, 191, 36)` | Warnings, debugging |
| `state_error` | `#EF4444` | `rgb(239, 68, 68)` | Errors, deleted, destructive actions |
| `state_info` | `#60A5FA` | `rgb(96, 165, 250)` | Links, modified, info states |

### Derived / Extended Palette (from `luigios-dark.ron`)
Use these for gradient stops, hover states, and surface layering where the core tokens are insufficient:

| Token | Hex | Usage |
|---|---|---|
| `neutral_1` | `#121416` | Equivalent to `surface_900` |
| `neutral_2` | `#1A1A1A` | Equivalent to `surface_800` |
| `neutral_3` | `#262626` | Equivalent to `surface_700` |
| `neutral_4` | `#404040` | Inactive borders, disabled states |
| `neutral_5` | `#666666` | Placeholder text |
| `neutral_6` | `#858585` | Separator lines |
| `neutral_7` | `#A3A3A3` | Subtle labels |
| `neutral_8` | `#C9D1D9` | Equivalent to `text_secondary` |
| `neutral_9` | `#E5E7EB` | Secondary headings |
| `neutral_10` | `#F5F7FA` | Equivalent to `text_primary` |
| `accent_blue` | `#60A5FA` | Equivalent to `state_info` |
| `accent_indigo` | `#818CF8` | Rare accents, mentions |
| `accent_purple` | `#A78BFA` | Agent-specific highlights |
| `accent_pink` | `#F472B6` | Agent-specific highlights |
| `accent_orange` | `#F97316` | Extended warm accent |
| `ext_warm_grey` | `#78716C` | Warm neutral |
| `ext_yellow` | `#FBBF24` | Equivalent to `state_warning` |
| `ext_blue` | `#60A5FA` | Equivalent to `state_info` |

---

## 2. Typography

| Role | Font Family | Fallback Stack |
|---|---|---|
| Display / Headings | **Exo 2** | `system-ui, sans-serif` |
| UI / Body | **Inter** | `system-ui, sans-serif` |
| Mono / Code | **JetBrains Mono** | `ui-monospace, monospace` |

- Import all three from Google Fonts.
- Use `Exo 2` for the theme name, headings, and accent labels.
- Use `Inter` for all body text, UI labels, and navigation.
- Use `JetBrains Mono` for code blocks, tool output, terminal emulation, and data displays.

---

## 3. Spacing & Radii

| Token | Value | Usage |
|---|---|---|
| `radius_small` | `6px` | Buttons, inputs, tags |
| `radius_medium` | `8px` | Cards, modals, panels |
| `safe_area_handheld` | `48px` | Mobile padding |
| `safe_area_television` | `72px` | TV / large-screen padding |

---

## 4. Theme Personality & Art Direction

- **Name:** `luigios-cosmic-workstation` (display as "LuigiOS Workstation")
- **Vibe:** Deep neutral surfaces, crisp green accents, generous hierarchy, compact controls, limited decorative motion.
- **Contrast target:** WCAG AA minimum (≥4.5:1 for body text, ≥3:1 for large text). The green `#22C55E` on `#000000` passes. The bright green `#66FF66` on `#000000` passes with a large margin.
- **Motion:** Prefer reduced motion where possible. No flashing animations.

---

## 5. OpenClaw TUI Theme JSON

Generate a complete TUI theme JSON file (`themes/luigios-cosmic-workstation.json`) with the following exact mappings. Do not invent new color keys; use only the documented `ThemeJson` schema.

### Required `colors` mapping

```json
{
  "name": "LuigiOS Workstation",
  "vars": {
    "colorScheme": "dark"
  },
  "colors": {
    "accent": "#22C55E",
    "border": "#262626",
    "borderAccent": "#66FF66",
    "borderMuted": "#1A1A1A",
    "success": "#22C55E",
    "error": "#EF4444",
    "warning": "#FBBF24",
    "muted": "#9CA3AF",
    "dim": "#9CA3AF",
    "text": "#F5F7FA",
    "thinkingText": "#C9D1D9",
    "selectedBg": "#000000",
    "userMessageBg": "#1A1A1A",
    "userMessageText": "#F5F7FA",
    "customMessageBg": "#121416",
    "customMessageText": "#F5F7FA",
    "customMessageLabel": "#66FF66",
    "toolPendingBg": "#121416",
    "toolSuccessBg": "#1A1A1A",
    "toolErrorBg": "#1A1A1A",
    "toolTitle": "#66FF66",
    "toolOutput": "#C9D1D9",
    "mdHeading": "#66FF66",
    "mdLink": "#22C55E",
    "mdLinkUrl": "#9CA3AF",
    "mdCode": "#66FF66",
    "mdCodeBlock": "#121416",
    "mdCodeBlockBorder": "#262626",
    "mdQuote": "#60A5FA",
    "mdQuoteBorder": "#1A1A1A",
    "mdHr": "#262626",
    "mdListBullet": "#22C55E",
    "toolDiffAdded": "#22C55E",
    "toolDiffRemoved": "#EF4444",
    "toolDiffContext": "#9CA3AF",
    "syntaxComment": "#9CA3AF",
    "syntaxKeyword": "#A78BFA",
    "syntaxFunction": "#60A5FA",
    "syntaxVariable": "#F5F7FA",
    "syntaxString": "#66FF66",
    "syntaxNumber": "#FBBF24",
    "syntaxType": "#FBBF24",
    "syntaxOperator": "#60A5FA",
    "syntaxPunctuation": "#C9D1D9",
    "thinkingOff": "#9CA3AF",
    "thinkingMinimal": "#9CA3AF",
    "thinkingLow": "#FBBF24",
    "thinkingMedium": "#FBBF24",
    "thinkingHigh": "#66FF66",
    "thinkingXhigh": "#66FF66",
    "bashMode": "#22C55E"
  },
  "export": {
    "pageBg": "#000000",
    "cardBg": "#121416",
    "infoBg": "#1A1A1A"
  }
}
```

### Design rules for the TUI theme
- All backgrounds must be OLED-friendly (`#000000` or `#121416`).
- `accent` (`#22C55E`) is the single source of truth for success, selection, and focus.
- `accent_bright` (`#66FF66`) is reserved for headings, active tool titles, and the cursor/selection highlight.
- Error state is always `#EF4444`. Warning is always `#FBBF24`. Info is always `#60A5FA`.
- Syntax highlighting uses the extended accent palette (indigo, blue, purple) to create hierarchy without breaking the green-primary rule.
- Thinking/reasoning indicators use `#FBBF24` (low/medium) and `#66FF66` (high/xhigh) to indicate increasing depth.

---

## 6. OpenClaw Control UI Theme (tweakcn / CSS Custom Properties)

Generate a tweakcn-compatible theme for the OpenClaw Control UI. The Control UI uses CSS custom properties. Provide the full CSS variable set and a tweakcn share link structure.

### CSS Variable Set

```css
:root {
  /* Surfaces */
  --bg-primary: #000000;
  --bg-secondary: #121416;
  --bg-tertiary: #1A1A1A;
  --bg-elevated: #262626;
  --bg-hover: rgba(34, 197, 94, 0.08);

  /* Borders */
  --border-default: #262626;
  --border-muted: #1A1A1A;
  --border-accent: #22C55E;
  --border-focus: #66FF66;

  /* Text */
  --text-primary: #F5F7FA;
  --text-secondary: #C9D1D9;
  --text-muted: #9CA3AF;
  --text-accent: #22C55E;
  --text-on-accent: #000000;

  /* Actions */
  --accent-primary: #22C55E;
  --accent-hover: #66FF66;
  --accent-active: #00B14B;
  --danger: #EF4444;
  --warning: #FBBF24;
  --info: #60A5FA;
  --success: #22C55E;

  /* Typography */
  --font-display: 'Exo 2', system-ui, sans-serif;
  --font-body: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;

  /* Radii */
  --radius-sm: 6px;
  --radius-md: 8px;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.5);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.6);
  --shadow-glow: 0 0 12px rgba(34, 197, 94, 0.25);
}
```

### tweakcn URL
Generate a tweakcn editor URL that imports this palette:
```
https://tweakcn.com/editor/theme?primary=22C55E&background=000000&foreground=F5F7FA&accent=66FF66&radius=8
```

### Design rules for Control UI
- Background is always `#000000` or `#121416`. No gray-blue.
- Sidebar and panels use `#121416`.
- Cards and modals use `#1A1A1A`.
- Borders are `#262626` (default) or `#22C55E` (focused/active).
- Buttons use `#22C55E` background with `#000000` text. Hover moves to `#66FF66`.
- Text is `#F5F7FA` primary, `#C9D1D9` secondary, `#9CA3AF` muted.
- Links and interactive text use `#22C55E`.
- Code and monospace content use `JetBrains Mono`.

---

## 7. OpenClaw Dashboard Theme (Third-Party `themes.json`)

Generate a Dashboard theme entry compatible with the OpenClaw Dashboard (`themes.json` format, 19 CSS variables).

### JSON Entry

```json
{
  "luigios-cosmic-workstation": {
    "name": "LuigiOS Workstation",
    "type": "dark",
    "icon": "🟢",
    "colors": {
      "bg": "#000000",
      "surface": "#121416",
      "surfaceHover": "#1A1A1A",
      "border": "#262626",
      "accent": "#22C55E",
      "accent2": "#66FF66",
      "green": "#22C55E",
      "yellow": "#FBBF24",
      "red": "#EF4444",
      "orange": "#F97316",
      "purple": "#A78BFA",
      "text": "#F5F7FA",
      "textStrong": "#FFFFFF",
      "muted": "#9CA3AF",
      "dim": "#666666",
      "darker": "#404040",
      "tableBg": "#121416",
      "tableHover": "#1A1A1A",
      "scrollThumb": "#262626"
    }
  }
}
```

### Design rules for Dashboard
- `bg` is `#000000` (OLED black).
- `surface` is `#121416` (sidebar, panels).
- `surfaceHover` is `#1A1A1A`.
- `accent` is `#22C55E` (primary actions, active nav).
- `accent2` is `#66FF66` (hover, highlights, badges).
- Table rows alternate between `#000000` and `#121416`.
- Scroll thumb is `#262626`.
- All text colors match the canonical tokens above.

---

## 8. Generation Instructions

### If using `ai-theme` (npm)
```bash
npx ai-theme --primary "#22C55E" --secondary "#121416" --accent "#66FF66" --dark-mode -f json -o themes/luigios-cosmic-workstation.json
```

Then refine the generated JSON to match the exact mappings in Section 5 above. `ai-theme` does not support all OpenClaw token names, so post-process the output.

### If using SeedFlip skill (`seedflip-theme`)
```
Generate an OpenClaw dashboard theme named "LuigiOS Workstation" with these colors:
- Background: #000000
- Surface: #121416
- Accent: #22C55E
- Accent2: #66FF66
- Text: #F5F7FA
- Muted: #9CA3AF
- Border: #262626
- Error: #EF4444
- Warning: #FBBF24
- Info: #60A5FA
Format: openclaw
```

### If using tweakcn for Control UI
1. Open `https://tweakcn.com/editor/theme`
2. Set primary to `#22C55E`, background to `#000000`, foreground to `#F5F7FA`
3. Adjust radius to `8px`
4. Export as CSS custom properties and merge with Section 6.

---

## 9. Validation Checklist

Before finalizing, verify:
- [ ] All hex values match the canonical `design-tokens-v1.json` exactly.
- [ ] TUI theme JSON passes `ThemeJson` schema validation.
- [ ] Control UI CSS variables cover every property in the OpenClaw Control UI.
- [ ] Dashboard `themes.json` entry has all 19 required color keys.
- [ ] WCAG AA contrast is met for all text-on-background pairs.
- [ ] Typography stack references `Exo 2`, `Inter`, and `JetBrains Mono` with correct fallbacks.
- [ ] No legacy color values (no `#65d46e` from the old manifest; always use `#22C55E`).

---

## 10. Output Artifacts

Produce exactly these files:

1. `themes/luigios-cosmic-workstation.json` — TUI theme
2. `themes/luigios-cosmic-workstation.css` — Control UI CSS custom properties
3. `themes/luigios-cosmic-workstation-dashboard.json` — Dashboard `themes.json` entry
4. `themes/README.md` — Installation and switching instructions

### README.md Template
```markdown
# LuigiOS Workstation — OpenClaw Theme

## Install
1. Copy `luigios-cosmic-workstation.json` to your OpenClaw themes directory.
2. Restart OpenClaw or run `/theme list` to verify.
3. Switch with: `openclaw tui --theme luigios-cosmic-workstation`

## Sources
- LuigiOS design tokens: `LuigiOS/branding/design-tokens-v1.json`
- OpenClaw ThemeJson schema: `dist/index-*.d.ts`

## Variant
CachyOS COSMIC Developer Workstation
```

---

*Generated from LuigiOS branding system. All color authority derives from `design-tokens-v1.json` and `manifest-v2.json`.*

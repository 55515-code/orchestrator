# OpenClaw Theme Generation Prompt — LuigiOS Art Style

## Role
You are generating a complete, production-ready OpenClaw theme package based on the **LuigiOS** design system (CachyOS COSMIC Developer Workstation variant). Output must cover **all three OpenClaw theme surfaces** — TUI terminal, Control UI web dashboard, and Dashboard third-party skin — plus any required artwork assets.

---

## 1. Art Direction & Identity

LuigiOS is a professional development operating system. The visual identity must read as technically precise, restrained, and high-contrast.

- **Vibe:** Deep neutral surfaces, crisp green accents, generous hierarchy, compact controls, limited decorative motion.
- **Identity span:** firmware-adjacent boot screens, recovery, COSMIC desktop, terminals, and editors.
- **Mascot:** The LuigiOS caretaker is always the same raccoon. Clothing, facial markings, body proportions, technical role, and calm competence remain stable across all variants. The angel variant adds a restrained pale-green luminous halo and small stylized light-feather wing shapes for recommended/safe states. The demon variant adds swept-back charcoal horns and a faint ember-red rim light for experimental/risky states. The illustration style is polished semi-flat system UI art with crisp hard outer contours and restrained interior texture.
- **Decentralized networking:** Visual language should feel understandable rather than mysterious. Show trust, connectivity, privacy exposure, quota, and contribution as separate states. Never imply that ordinary peer transport is anonymous or that peer availability is equivalent to release authorization.
- **Accessibility:** Preserve strong text contrast, visible focus states, semantic error/warning colors, and non-color status cues. Prefer standard application symbols from Papirus; custom icons are reserved for LuigiOS-owned surfaces.
- **Motion:** Prefer reduced motion where possible. No flashing animations.

---

## 2. Canonical LuigiOS Color Tokens (Source of Truth)

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

## 3. Typography

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

## 4. Spacing & Radii

| Token | Value | Usage |
|---|---|---|
| `radius_small` | `6px` | Buttons, inputs, tags |
| `radius_medium` | `8px` | Cards, modals, panels |
| `safe_area_handheld` | `48px` | Mobile padding |
| `safe_area_television` | `72px` | TV / large-screen padding |

---

## 5. Mascot & Art References

### Core Mascot Identity
The LuigiOS caretaker is a raccoon. Stable identity traits across all variants:
- Dark gray fur, black raccoon face mask, pointed ears, ringed tail visible
- Practical charcoal utility jacket and small technical gear
- Calm, capable, focused expression — not cute, not monstrous, not human
- Polished semi-flat system UI illustration style with crisp hard outer contour and restrained interior texture

### Angel Variant (safe/recommended states)
- Restrained pale-green luminous halo (`#66FF66`)
- Small stylized light-feather wing shapes behind shoulders
- Use for: recommended defaults, successful validation, backups, restore points, safe mode, rollback, recoverable actions

### Demon Variant (experimental/risky states)
- Swept-back charcoal horns between the ears
- Faint ember-red rim light (`#EF4444` only on horns/rim details)
- Confident, knowing expression — mischievous but trustworthy
- Use for: developer controls, experimental features, destructive operations, unsigned content warnings, actions that cannot be automatically reversed

### Key Art Source Files
Reference these existing assets when generating new artwork:
- `LuigiOS/branding/source/caretaker-network-master.png` — master mascot identity reference
- `LuigiOS/branding/source/caretaker-angel-chroma.png` — angel chroma-key source
- `LuigiOS/branding/source/caretaker-demon-chroma.png` — demon chroma-key source
- `LuigiOS/branding/assets/mascot/caretaker-angel.png` — angel mascot asset
- `LuigiOS/branding/assets/mascot/caretaker-demon.png` — demon mascot asset
- `LuigiOS/branding/assets/core/luigios-logo.svg` — full wordmark
- `LuigiOS/branding/assets/core/luigios-symbolic.svg` — symbolic mark (small sizes)
- `LuigiOS/branding/assets/boot/luigios-splash.mp4` — boot splash video
- `LuigiOS/branding/assets/boot/luigios-splash-frame.png` — boot splash still
- `LuigiOS/branding/assets/boot/boot-logo-4x3.png` — boot logo
- `LuigiOS/branding/assets/boot/boot-logo-1280x800.png` — boot logo HD
- `LuigiOS/branding/assets/desktop/wallpapers/luigios/1920x1080.png` — desktop wallpaper
- `LuigiOS/branding/assets/desktop/wallpapers/luigios/1280x800.png` — desktop wallpaper SD
- `LuigiOS/branding/assets/community/banner-1920x480.png` — community banner
- `LuigiOS/branding/assets/community/avatar-512.png` — community avatar

### Icon System
- Base layer: Papirus Dark (standard application symbols)
- Overlay: LuigiOS-specific icons with coherent green folders and original core application/launcher glyphs
- Custom icons reserved for LuigiOS-owned surfaces only

---

## 6. Theme Personality

- **Name:** `luigios-cosmic-workstation` (display as "LuigiOS Workstation")
- **Vibe:** Deep neutral surfaces, crisp green accents, generous hierarchy, compact controls, limited decorative motion.
- **Contrast target:** WCAG AA minimum (≥4.5:1 for body text, ≥3:1 for large text). The green `#22C55E` on `#000000` passes. The bright green `#66FF66` on `#000000` passes with a large margin.
- **Motion:** Prefer reduced motion where possible. No flashing animations.

---

## 7. OpenClaw TUI Theme JSON

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

## 8. OpenClaw Control UI Theme (CSS Custom Properties)

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

## 9. OpenClaw Dashboard Theme (Third-Party `themes.json`)

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

## 10. Image & Artwork Generation Prompts

Use these prompts when generating new visual assets. All image generation must use the chroma-key background (`#FF00FF`) for mascot variants so they can be cleanly extracted.

### Caretaker Angel Variant
```
Use case: stylized-concept
Asset type: LuigiOS interface mascot state plate, angel/safe variant
Input image: reference image for the exact original caretaker raccoon mascot, dark technical illustration style, facial mask markings, proportions, utility clothing, backpack, and calm capable personality
Primary request: create a clean waist-up character portrait of the SAME raccoon caretaker as an angel variant for recommended, protected, successful, backup, and recovery states
Subject: unmistakably a raccoon, same dark gray fur, black raccoon face mask, pointed ears, ringed tail visible, practical charcoal utility jacket and small technical gear; add one restrained pale-green luminous halo and two small stylized light-feather wing shapes attached behind the shoulders; kind focused expression, not cute baby-like, not human
Composition: centered single character, generous padding, readable at small UI sizes, silhouette fully inside canvas
Style: polished semi-flat system UI illustration with crisp hard outer contour and restrained interior texture, closely matching the reference's serious dark technical caretaker aesthetic
Color palette: charcoal, gray, white highlights, LuigiOS greens #22C55E and #66FF66; no other dominant hues
Background: perfectly flat solid #FF00FF chroma-key background for later removal; uniform color, no shadows, gradients, texture, floor, reflections, glow spill, or lighting variation in the background
Constraints: same mascot identity as reference; no logos, no words, no text, no watermark, no copyrighted character resemblance, no vendor marks; no #FF00FF anywhere in the character; no cast shadow; crisp separated edges suitable for chroma-key removal
```

### Caretaker Demon Variant
```
Use case: stylized-concept
Asset type: LuigiOS interface mascot state plate, demon/advanced variant
Input image: reference image for the exact original caretaker raccoon mascot, dark technical illustration style, facial mask markings, proportions, utility clothing, backpack, and calm capable personality
Primary request: create a clean waist-up character portrait of the SAME raccoon caretaker as a demon variant for expert, experimental, risky, destructive, and irreversible settings
Subject: unmistakably a raccoon, same dark gray fur, black raccoon face mask, pointed ears, ringed tail visible, practical charcoal utility jacket and small technical gear; add two small swept-back charcoal horns between the ears, a restrained dark pointed tail-tip cue integrated with the natural ringed raccoon tail, and a faint ember-red rim light; confident knowing expression, mischievous but trustworthy, not evil, not monstrous, not human
Composition: centered single character, generous padding, readable at small UI sizes, silhouette fully inside canvas
Style: polished semi-flat system UI illustration with crisp hard outer contour and restrained interior texture, closely matching the reference's serious dark technical caretaker aesthetic and the paired angel state plate
Color palette: charcoal, gray, pale neutral highlights, LuigiOS green #22C55E for existing technical gear, restrained warning red #EF4444 only on horns/rim details; no other dominant hues
Background: perfectly flat solid #FF00FF chroma-key background for later removal; uniform color, no shadows, gradients, texture, floor, reflections, glow spill, or lighting variation in the background
Constraints: same mascot identity as reference; no logos, no words, no text, no watermark, no copyrighted character resemblance, no vendor marks; no #FF00FF anywhere in the character; no cast shadow; crisp separated edges suitable for chroma-key removal
```

### Boot Splash / Wallpaper Style Prompt
```
Use case: stylized-concept
Asset type: LuigiOS boot splash or desktop wallpaper, dark technical system UI art
Subject: professional development operating system boot screen or wallpaper featuring the LuigiOS raccoon caretaker in a restrained, technically precise composition
Style: polished semi-flat system UI illustration, dark technical aesthetic, crisp hard outer contours, restrained interior texture, no photorealism, no cartoonish exaggeration
Color palette: deep neutral surfaces (#000000, #121416, #1A1A1A), crisp green accents (#22C55E, #66FF66), high contrast, OLED-friendly
Composition: clean, centered, generous negative space, readable at small UI sizes, no clutter
Mood: calm competence, technical precision, professional identity, accessible and inviting
Constraints: no logos, no words, no text, no watermark, no copyrighted character resemblance, no vendor marks; no flashing elements; reduced-motion safe
```

---

## 11. Generation Instructions

### TUI Theme JSON
Place the generated JSON at `themes/luigios-cosmic-workstation.json` in the OpenClaw themes directory. Validate against the `ThemeJson` schema (40 required color tokens).

### Control UI CSS
Place the generated CSS at `themes/luigios-cosmic-workstation.css`. Import into Control UI via the Appearance panel or tweakcn share link.

### Dashboard Theme
Merge the JSON entry into your `themes.json` file under the `themes` key.

### Image Assets
Generate mascot variants and artwork using the prompts in Section 10. Always use `#FF00FF` chroma-key backgrounds for mascot portraits so they can be extracted cleanly. Save final assets to the paths declared in `LuigiOS/branding/`.

---

## 12. Validation Checklist

Before finalizing, verify:
- [ ] All hex values match the canonical `design-tokens-v1.json` exactly.
- [ ] TUI theme JSON passes `ThemeJson` schema validation (40 required color tokens).
- [ ] Control UI CSS variables cover every property in the OpenClaw Control UI.
- [ ] Dashboard `themes.json` entry has all 19 required color keys.
- [ ] WCAG AA contrast is met for all text-on-background pairs.
- [ ] Typography stack references `Exo 2`, `Inter`, and `JetBrains Mono` with correct fallbacks.
- [ ] No legacy color values (no `#65d46e` from the old manifest; always use `#22C55E`).
- [ ] Mascot variants maintain consistent raccoon identity across all states.
- [ ] No `#FF00FF` leak in final mascot assets (chroma key must be fully removed).
- [ ] All generated images have no text, logos, watermarks, or vendor marks.

---

## 13. Output Artifacts

Produce exactly these files:

1. `themes/luigios-cosmic-workstation.json` — TUI theme
2. `themes/luigios-cosmic-workstation.css` — Control UI CSS custom properties
3. `themes/luigios-cosmic-workstation-dashboard.json` — Dashboard `themes.json` entry
4. `themes/README.md` — Installation and switching instructions
5. Artwork assets (if generating images) — mascot variants, logos, icons per Section 10

### README.md Template
```markdown
# LuigiOS Workstation — OpenClaw Theme

## Install
1. Copy `luigios-cosmic-workstation.json` to your OpenClaw themes directory.
2. Restart OpenClaw or verify theme discovery.
3. Switch via OpenClaw theme settings or theme API.

## Sources
- LuigiOS design tokens: `LuigiOS/branding/design-tokens-v1.json`
- OpenClaw ThemeJson schema: `dist/index-*.d.ts`

## Variant
CachyOS COSMIC Developer Workstation
```

---

## 14. Source References

Canonical LuigiOS branding files that authority this theme:

- `LuigiOS/branding/design-tokens-v1.json` — canonical color, spacing, typography tokens
- `LuigiOS/branding/manifest-v2.json` — product manifest and surface list
- `LuigiOS/branding/ART_DIRECTION.md` — art direction and identity rules
- `LuigiOS/branding/MASCOT.md` — mascot usage and variant rules
- `LuigiOS/branding/README.md` — visual system overview
- `LuigiOS/branding/cosmic-rice/README.md` — COSMIC rice design details
- `LuigiOS/branding/prompts/caretaker-angel.md` — angel variant generation prompt
- `LuigiOS/branding/prompts/caretaker-demon.md` — demon variant generation prompt
- `LuigiOS/branding/source/caretaker-network-master.png` — mascot identity reference
- `LuigiOS/branding/source/caretaker-angel-chroma.png` — angel chroma-key source
- `LuigiOS/branding/source/caretaker-demon-chroma.png` — demon chroma-key source
- `LuigiOS/branding/assets/core/luigios-logo.svg` — full wordmark
- `LuigiOS/branding/assets/core/luigios-symbolic.svg` — symbolic mark
- `LuigiOS/branding/assets/mascot/caretaker-angel.png` — angel mascot asset
- `LuigiOS/branding/assets/mascot/caretaker-demon.png` — demon mascot asset
- `LuigiOS/branding/assets/boot/luigios-splash.mp4` — boot splash video
- `LuigiOS/branding/assets/boot/luigios-splash-frame.png` — boot splash still
- `LuigiOS/branding/assets/boot/boot-logo-4x3.png` — boot logo
- `LuigiOS/branding/assets/boot/boot-logo-1280x800.png` — boot logo HD
- `LuigiOS/branding/assets/desktop/wallpapers/luigios/1920x1080.png` — desktop wallpaper
- `LuigiOS/branding/assets/desktop/wallpapers/luigios/1280x800.png` — desktop wallpaper SD
- `LuigiOS/branding/assets/community/banner-1920x480.png` — community banner
- `LuigiOS/branding/assets/community/avatar-512.png` — community avatar
- `LuigiOS/branding/cosmic-rice/luigios-dark.ron` — COSMIC theme color definitions
- `LuigiOS/branding/cosmic-rice/vscode-theme/themes/luigios-workstation-color-theme.json` — VS Code color theme
- `LuigiOS/docs/BRANDING.md` — branding deployment rules
- `LuigiOS/docs/PRODUCT_PRINCIPLES.md` — product principles including professional identity

---

*Generated from LuigiOS branding system. All color authority derives from `design-tokens-v1.json` and `manifest-v2.json`.*

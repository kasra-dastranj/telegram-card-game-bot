---
name: Cyber-Pulse
colors:
  surface: '#0f102c'
  surface-dim: '#0f102c'
  surface-bright: '#363654'
  surface-container-lowest: '#0a0b26'
  surface-container-low: '#181934'
  surface-container: '#1c1d39'
  surface-container-high: '#262744'
  surface-container-highest: '#31324f'
  on-surface: '#e1e0ff'
  on-surface-variant: '#cac4d6'
  inverse-surface: '#e1e0ff'
  inverse-on-surface: '#2d2e4b'
  outline: '#938ea0'
  outline-variant: '#484554'
  surface-tint: '#cbbeff'
  primary: '#cbbeff'
  on-primary: '#330098'
  primary-container: '#7b5eea'
  on-primary-container: '#ffffff'
  inverse-primary: '#6343d0'
  secondary: '#f0c040'
  on-secondary: '#3e2e00'
  secondary-container: '#b88d00'
  on-secondary-container: '#392a00'
  tertiary: '#ffb86e'
  on-tertiary: '#492900'
  tertiary-container: '#ac6600'
  on-tertiary-container: '#ffffff'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e6deff'
  primary-fixed-dim: '#cbbeff'
  on-primary-fixed: '#1d0061'
  on-primary-fixed-variant: '#4a25b7'
  secondary-fixed: '#ffdf97'
  secondary-fixed-dim: '#f0c040'
  on-secondary-fixed: '#251a00'
  on-secondary-fixed-variant: '#5a4400'
  tertiary-fixed: '#ffdcbd'
  tertiary-fixed-dim: '#ffb86e'
  on-tertiary-fixed: '#2c1600'
  on-tertiary-fixed-variant: '#693c00'
  background: '#0f102c'
  on-background: '#e1e0ff'
  surface-variant: '#31324f'
  background-deep: '#0A0A1A'
  surface-card: '#12122A'
  rarity-normal: '#4CAF50'
  rarity-epic: '#9C27B0'
  rarity-legend: '#FF9800'
  rarity-rare: '#F44336'
  text-primary: '#FFFFFF'
typography:
  headline-lg:
    fontFamily: Oswald
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: 0.02em
  headline-md:
    fontFamily: Oswald
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-sm:
    fontFamily: Oswald
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 28px
  body-lg:
    fontFamily: Vazirmatn
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Vazirmatn
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  stat-numeric:
    fontFamily: Rajdhani
    fontSize: 18px
    fontWeight: '700'
    lineHeight: 20px
    letterSpacing: 0.05em
  label-caps:
    fontFamily: Rajdhani
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.1em
  button-label:
    fontFamily: Oswald
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 12px
  margin-mobile: 16px
  card-gap: 8px
  section-padding: 24px
---

## Brand & Style

The design system is engineered for a competitive, high-stakes Telegram Mini App environment. It balances a **Dark Gamer/Cyberpunk** aesthetic with the functional clarity required for a collectible card game (CCG). The brand personality is aggressive, energetic, and atmospheric, utilizing deep void-like backgrounds contrasted against neon-infused interactive elements and metallic gold accents.

The visual style is a hybrid of **Minimalism** and **Glassmorphism**:
- **Minimalism** provides the structural rigour and spacing needed for data-heavy card stats.
- **Glassmorphism** is applied through semi-transparent card surfaces and background blurs to create depth and a high-tech "HUD" (Heads-Up Display) feel.
- **High-Contrast** elements, specifically rarity-based glows and vibrantly colored action buttons, ensure that the most important game states are immediately legible in a mobile-first, rapid-play context.

## Colors

The palette is optimized for OLED screens, using a deep navy-black base to make chromatic elements "pop." 

- **Primary (#7B5EEA):** Used for the most critical game actions (e.g., "Start Battle"). It represents the energy and "pulse" of the game.
- **Secondary/Accent (#F0C040):** Reserved for prestige elements, currency (Coins), and highlighting the current player's selection.
- **Rarity Colors:** These are fixed semantic tokens. They must be used for card borders, glow effects, and difficulty indicators to provide instant cognitive recognition of value.
- **Surface Strategy:** Backgrounds use `#0A0A1A`, while interactive containers and card bodies use `#12122A` to create a subtle layered hierarchy without needing heavy shadows.

## Typography

This system employs a dual-language strategy to support both high-energy gaming aesthetics and RTL (Persian) readability.

- **English/Decorative (Oswald/Rajdhani):** Use **Oswald** for high-impact headlines and primary buttons. Use **Rajdhani** for technical data, stats, and numeric labels to evoke a futuristic, condensed "tech" feel.
- **Persian/Body (Vazirmatn):** Use for all descriptive text, instructions, and UI labels where RTL support is required. Vazirmatn's clean strokes ensure legibility at small sizes on mobile.
- **Visual Hierarchy:** Numbers (stats) should always be rendered in Rajdhani even within Persian contexts to maintain the "cyber" data aesthetic.

## Layout & Spacing

The layout follows a **fluid grid** model optimized for the Telegram Webview environment.

- **Rhythm:** A 4px base unit governs all dimensions.
- **Grid:** Use a 2-column grid for selection screens (Arena/Difficulty) and a horizontal-scroll "carousel" for card collections.
- **Safe Zones:** Content must maintain a 16px side margin to avoid clipping on various mobile handset aspect ratios.
- **RTL Handling:** Layouts must flip horizontally when the language is set to Persian. This includes the placement of icons relative to text and the direction of progress bar fills (XP).

## Elevation & Depth

Hierarchy is achieved through **Tonal Layers** and **Neon Glows** rather than traditional shadows.

- **Base Layer:** `#0A0A1A` (The void).
- **Surface Layer:** `#12122A` with a 1px inner border of `#FFFFFF` at 10% opacity.
- **Interactive Depth:** Active cards or selected items utilize an outer glow (`box-shadow`) using their respective rarity color or the primary purple.
- **Overlays:** Modals and slide-up panels use a backdrop blur (12px) to dim the background game state, creating a focused "Glassmorphic" stack.

## Shapes

The shape language is "Soft-Tech"—moderately rounded to feel modern and premium, but not "bubbly."

- **Standard Elements:** 0.5rem (8px) for cards, container sections, and input fields.
- **Large Elements:** 1rem (16px) for major modal containers and bottom sheets.
- **Small Elements:** 0.25rem (4px) for rarity tags and small stat badges.
- **Buttons:** Use high roundedness (1rem or pill) for primary CTAs to make them feel distinct from the rectangular card units.

## Components

### Trading Cards
- **Small:** 80x80px. Focus on the sticker/artwork and a rarity border.
- **Large (Detailed):** 12px rounded corners. Header contains the name and rarity icon. Body displays stats (⚡, 🏃, 🧠, ⭐) in a 2x2 grid using `stat-numeric` typography.
- **States:** Highlighted (Gold border), Used (60% opacity with grayscale filter), Victory (Pulsing glow).

### Action Buttons
- **Primary:** Background `#7B5EEA`, text `#FFFFFF`, uppercase `button-label`. 12px vertical padding.
- **Secondary:** Outlined with 1px `#8888AA`, text `#8888AA`.

### Progress Bars (XP)
- Track: `#12122A` (surface).
- Fill: Linear gradient from `#7B5EEA` to a lighter violet.
- Height: 8px for standard, 4px for mini-indicators.

### Status Indicators (Hearts/Coins)
- Icon followed by `stat-numeric` text.
- Hearts: Red `#F44336`.
- Coins: Gold `#F0C040`.

### Input Fields
- Background: `#12122A`.
- Border: 1px solid `#8888AA` at 30% opacity.
- RTL: Text alignment must switch for Persian input.
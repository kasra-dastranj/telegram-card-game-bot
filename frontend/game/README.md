# TelBattle Arena Mini App

Phaser-based Telegram Mini App vertical slice. Phaser renders the arena and card
effects; accessible HTML controls handle navigation, card selection, and actions.

## Local preview

Start the Flask API from the repository root:

```powershell
python -m web.miniapp_api
```

Then start Vite from this directory:

```powershell
npm install
npm run dev
```

Open `http://127.0.0.1:5173/?demo=1` for the deterministic visual demo, or omit
`?demo=1` to use the Flask API and debug user.

## Production build

```powershell
npm run build
```

Flask serves `dist/index.html` at `/` and `/miniapp`, Vite assets at
`/miniapp-assets/*`, and optimized card artwork at `/card-images/*`.

## Current scope

- Solo lobby, difficulty selection, card selection, battle, and result flow
- Telegram init data header and haptic integration
- Mobile portrait and landscape layouts
- Reduced-motion support and 44px minimum touch targets

Quick and PvP modes still need dedicated API endpoints before they can be added
to this client.

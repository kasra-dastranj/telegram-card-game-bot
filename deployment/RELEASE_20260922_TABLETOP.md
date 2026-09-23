# TelBattle tabletop UI — deployed 2026-09-22

- Public entry: `https://89-106-206-220.nip.io/miniapp`
- Active release: `/opt/telbattle/releases/20260922-tabletop-ui-v1`
- Previous release (retained): `/opt/telbattle/releases/20260901-arena-registry-v5`
- Scope: the previously built and tested frontend, including bundled fonts and media.
- The new release was copied from the live release before the frontend was overlaid.
  No local backend changes were deployed. No database migration was run.
- `/opt/telbattle/current` was switched atomically. No service restart was needed:
  `MINIAPP_DIST_DIR` already points through `current`. API PID stayed `475372`.
- Shared database, card images, and uploaded arena media remain untouched.

## Verification

Public HTTPS responses matched the local build byte-for-byte:

| File | SHA-256 |
| --- | --- |
| index.html | `5ece355bf6ad99f56caaadc9c819ad8cc73c1cfc8481e40cb60864df56419903` |
| assets/index-BUgaa4ak.js | `c4f31eb2730e80cf023443312654b53f05ba62eec2b5baa8e1b22bc838a21c03` |
| assets/index-Cy32u_uY.css | `48b5b60fda843cb30d7530c654e4e63647612201cb7ae8c317bfbada4f366839` |

Health endpoint, Vazirmatn font, splash image, and city arena image returned HTTP 200.
`telbattle-api`, `telbattle-bot`, and `telbattle-admin` remained active.
This release check validates public delivery and service health; prior browser
tests were local, not an authenticated Telegram-device session.

## Rollback

First verify `current` still resolves to this release (do not overwrite a newer
deployment). Create a fresh temporary symlink to the previous release, then use
`mv -Tf` to atomically replace `/opt/telbattle/current`. Confirm the health endpoint
and previous index afterward. No database rollback or service restart is required
for this frontend-only release.

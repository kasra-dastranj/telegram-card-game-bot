# TelBattle — Codex import instructions (READ FIRST)

## Task
This bundle contains Persian 3-line in-game bios and victory lines for **60 existing** character card entries. Do not create new character entities blindly. The Kooman card is **one combined card** for Kourosh and Iman; TMNT is **one card** for the four turtles.

## IMPORTANT: Discussion + dry run first. Do not mutate production.
1. Inspect existing backend models, Admin Panel, card character identifiers, translations, and random-win-line selection for Deck/Easy (and other modes only if they already support victory lines).
2. Map `temporary_id` + Persian name to existing canonical character IDs. Present the full mapping and conflicts; NEVER match on arbitrary fuzzy names without confirmation.
3. Determine if biography is per character or card variant. Default: one bio per character (shared Normal/Epic/Legend), unless existing schema dictates otherwise.
4. Determine whether victory lines currently belong to character, Legend avatar, player, or card variant, and reconcile with the game owner's rules; don't silently change existing victory rendering.
5. Use `telbattle_lore.json` as authoritative data. CSV files are editable alternatives. Exactly **three bio lines** per character, and **5 or 6** victory lines per character. The system should choose at random from all ACTIVE eligible lines; don't invent a fixed limit of five.
6. **Text distinction:** `original_game_line` is creative original copy for TelBattle, NOT a real quote said by the character. `verified_short_quote` includes a source URL and is an attributed *short quotation* that still requires an IP/license review before commercial deployment. Do NOT blindly import short third-party quotes to production until approved. Do not assume using the corresponding actor's voice is permitted.
7. `review_note` flags names and meme figures that need manual review. Preserve those notes and provide a list of unresolved items. Avoid claiming uncertain biography details as verified.
8. Safely handle RTL, UTF-8 Unicode, multiline bio, escaping apostrophes, and line endings. All CSV are UTF-8 with BOM for Excel convenience.
9. If import is approved, implement a reversible, idempotent import/upsert keyed on canonical existing IDs plus stable victory-line mapping; no deletion of other character metadata, existing victory lines, player holdings, Shop or economy state without explicit owner direction. Add backups, rollback and tests.
10. For victory quotes in English preserve English text when well-known. Do not silently machine-translate quotations.

## Data files
- `telbattle_lore.json`: normalized single-file source of truth.
- `characters_biographies.csv`: 3-line bios.
- `victory_lines.csv`: one line per row, with provenance and permission status.
- `TelBattle_Bios_and_Victory_Lines_FA.md`: readable manuscript for manual copy editing.
- `TelBattle_Lore_Editor.xlsx`: editable workbook.
- `VALIDATION.json`: automatic structural checks.

## Report back BEFORE writing code
- Mapped character ids and missing characters
- Existing database fields that will be reused versus newly added
- Proposed normalization/storage and avatar-related victory logic
- Quote/licensing items requiring approval
- Test plan and the exact dry-run results

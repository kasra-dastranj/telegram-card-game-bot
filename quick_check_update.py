import sqlite3
import uuid
from game_core import DatabaseManager, Card, CardRarity


def main():
    db = DatabaseManager()

    test_id = str(uuid.uuid4())
    test_name = f"AgentCheckCard_{test_id[:8]}"

    card = Card(
        card_id=test_id,
        name=test_name,
        rarity=CardRarity.NORMAL,
        power=10,
        speed=20,
        iq=30,
        popularity=40,
        abilities=["init"],
        biography="bio0",
        image_path=""
    )

    print("[1] Adding test card...")
    added = db.add_card(card)
    print(f"    added={added}")
    if not added:
        print("    Card add failed (maybe duplicate?). Exiting.")
        return

    print("[2] Updating abilities + biography...")
    updated = db.update_card(
        test_id,
        abilities=["alpha", "beta"],
        biography="bio1"
    )
    print(f"    updated={updated}")

    print("[3] Fetching updated card (ORM path)...")
    fetched = db.get_card_by_id(test_id)
    if fetched:
        print(f"    biography={fetched.biography}")
        print(f"    abilities(type)={type(fetched.abilities).__name__}, value={fetched.abilities}")
    else:
        print("    Failed to fetch card by id")

    print("[4] Raw DB check for abilities column...")
    conn = sqlite3.connect(db.db_path)
    cur = conn.cursor()
    cur.execute("SELECT abilities, biography FROM cards WHERE card_id=?", (test_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        raw_abilities, raw_bio = row
        print(f"    raw abilities (DB)={raw_abilities}")
        print(f"    raw biography (DB)={raw_bio}")
    else:
        print("    Raw select failed: no row")

    print("[5] Cleanup: deleting test card...")
    deleted = db.delete_card(test_id)
    print(f"    deleted={deleted}")


if __name__ == "__main__":
    main()

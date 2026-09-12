from pathlib import Path

from wardrobe_planner.data.seed_loader import load_seed_dataset

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    dataset = load_seed_dataset(ROOT / "data" / "seed")
    item_counts = {
        member.name: sum(item.member_id == member.id for item in dataset.wardrobe_items)
        for member in dataset.family_members
    }
    print("Seed dataset is valid.")
    print(f"Household: {dataset.household.name}")
    print(f"Members: {len(dataset.family_members)}")
    print(f"Wardrobe items: {len(dataset.wardrobe_items)} ({item_counts})")
    print(f"Events: {len(dataset.events)}")
    print(f"Guidance documents: {len(dataset.guidance_documents)}")
    print(f"Catalog items: {len(dataset.catalog_items)}")


if __name__ == "__main__":
    main()

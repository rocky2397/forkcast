"""Shopping basket (D21): greedy set cover, and the honesty of its counts."""

from app import recipes, shopping


def test_picks_the_ingredient_that_unlocks_most(db):
    items, _ = shopping.suggest(db, basket_size=1)
    # yeast completes 3 and 4 on its own; milk only completes 6.
    assert items[0]["canonical"] == "yeast"
    assert items[0]["unlocks"] == 2


def test_later_picks_count_recipes_the_earlier_ones_also_needed(db):
    """Recipe 5 needs yeast AND milk: it may only be credited once, to milk."""
    items, _ = shopping.suggest(db, basket_size=2)
    assert [i["canonical"] for i in items] == ["yeast", "milk"]
    assert items[1]["unlocks"] == 2  # recipe 6 (milk alone) + recipe 5 (with yeast)


def test_counts_are_disjoint_and_match_real_coverage(db):
    """The guard against double-counting: claimed total == actual recipes covered."""
    items, _ = shopping.suggest(db, basket_size=3)
    basket = {i["canonical"] for i in items}
    pool = recipes.missing_sets(db, max_missing=3)
    covered = [r for r in pool if r["missing"] <= basket]
    assert sum(i["unlocks"] for i in items) == len(covered)


def test_stops_when_nothing_is_left_to_unlock(db):
    """Asking for more items than the corpus can use must not invent picks."""
    items, _ = shopping.suggest(db, basket_size=5, max_missing=1)
    assert [i["canonical"] for i in items] == ["yeast", "milk"]


def test_max_missing_limits_how_far_ahead_it_shops(db):
    items, _ = shopping.suggest(db, basket_size=3, max_missing=1)
    # Recipe 7 needs three things, so none of them is ever one purchase away.
    assert "duck" not in {i["canonical"] for i in items}


def test_examples_name_recipes_the_pick_actually_unlocks(db):
    items, _ = shopping.suggest(db, basket_size=1)
    names = {r["name"] for r in recipes.missing_sets(db, max_missing=3)
             if r["missing"] == frozenset({"yeast"})}
    assert set(items[0]["examples"]) <= names


def test_empty_inventory_still_produces_a_basket(db):
    db.executescript("DELETE FROM inventory")
    db.commit()
    items, _ = shopping.suggest(db, basket_size=3)
    assert items and all(i["unlocks"] > 0 for i in items)


def test_no_suggestions_when_everything_is_cookable(db):
    db.executescript("DELETE FROM recipe_ingredients WHERE canonical NOT IN "
                     "('chicken','rice','onion','carrot','egg')")
    db.commit()
    items, truncated = shopping.suggest(db, basket_size=3)
    assert items == [] and truncated is False


def test_truncation_is_reported_not_hidden(db, monkeypatch):
    """A silent cap would read as full coverage; D21 exposes it instead."""
    monkeypatch.setattr(shopping, "POOL_LIMIT", 1)
    _, truncated = shopping.suggest(db, basket_size=1)
    assert truncated is True

"""Cookability queries: the feed's foundation (D3) and shopping's input (D21)."""

from app import recipes


def test_cookable_now_lists_only_fully_stocked_recipes(db):
    ids = {r["id"] for r in recipes.cookable(db, max_missing=0)}
    # 1 needs chicken/rice/onion (all stocked); 2 needs rice + salt, a staple.
    assert ids == {1, 2}


def test_staples_are_assumed_present_unless_told_otherwise(db):
    without = {r["id"] for r in recipes.cookable(db, max_missing=0, assume_staples=False)}
    assert 2 not in without  # salt is suddenly a real missing ingredient
    assert 1 in without


def test_missing_names_are_reported_for_almost_cookable(db):
    by_id = {r["id"]: r for r in recipes.cookable(db, max_missing=1)}
    assert by_id[3]["missing"] == ["yeast"]
    assert by_id[3]["ingredients_missing"] == 1
    assert 5 not in by_id  # needs yeast *and* milk


def test_partially_normalized_recipes_are_excluded(db):
    """An unmatched ingredient can never be in inventory, so the recipe would
    look permanently uncookable rather than almost-cookable."""
    db.execute("UPDATE recipes SET matched_frac = 0.5 WHERE id = 1")
    db.commit()
    assert 1 not in {r["id"] for r in recipes.cookable(db, max_missing=0)}


def test_missing_sets_skips_what_is_already_cookable(db):
    pool = {r["id"]: r["missing"] for r in recipes.missing_sets(db, max_missing=3)}
    assert 1 not in pool and 2 not in pool  # nothing to buy for these
    assert pool[3] == frozenset({"yeast"})
    assert pool[5] == frozenset({"yeast", "milk"})
    assert pool[7] == frozenset({"duck", "potato", "thyme"})


def test_missing_sets_respects_max_missing(db):
    pool = recipes.missing_sets(db, max_missing=1)
    assert all(len(r["missing"]) == 1 for r in pool)
    assert {r["id"] for r in pool} == {3, 4, 6}


def test_inventory_changes_shift_what_is_cookable(db):
    """The guarantee D19 leans on: depleting an item re-locks its recipes."""
    assert 1 in {r["id"] for r in recipes.cookable(db, max_missing=0)}
    db.execute("DELETE FROM inventory WHERE canonical = 'chicken'")
    db.commit()
    assert 1 not in {r["id"] for r in recipes.cookable(db, max_missing=0)}

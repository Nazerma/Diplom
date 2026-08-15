from gemini import filter_product_ids


def test_filter_product_ids_discards_values_outside_candidates():
    candidates = [{"id": 2}, {"id": 5}]

    assert filter_product_ids([5, 999, 2], candidates) == [5, 2]

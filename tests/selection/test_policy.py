from archivenetwork.selection.policy import DefaultPolicy


def test_cap_enforced_at_max():
    policy = DefaultPolicy(max_per_album=3)
    assert policy.can_select("111", 2) is True
    assert policy.can_select("111", 3) is False


def test_non_album_not_selectable_by_default():
    assert DefaultPolicy().non_album_selectable() is False


def test_uncapped_album_ignores_max():
    policy = DefaultPolicy(max_per_album=3, uncapped_albums=frozenset({"555"}))
    assert policy.can_select("555", 99) is True  # special album: never full
    assert policy.can_select("111", 3) is False  # normal album: still capped

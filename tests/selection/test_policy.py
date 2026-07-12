from archivenetwork.selection.policy import DefaultPolicy


def test_cap_enforced_at_max():
    policy = DefaultPolicy(max_per_album=3)
    assert policy.can_select("111", 2) is True
    assert policy.can_select("111", 3) is False


def test_non_album_and_videos_are_selectable():
    # Nothing is auto-kept: both buckets must be pickable, or the user could never ship them.
    policy = DefaultPolicy(max_per_album=3)
    assert policy.can_select("__non_album__", 0) is True
    assert policy.can_select("__videos__", 999) is True  # videos are uncapped


def test_uncapped_album_ignores_max():
    policy = DefaultPolicy(max_per_album=3, uncapped_albums=frozenset({"555"}))
    assert policy.can_select("555", 99) is True  # special album: never full
    assert policy.can_select("111", 3) is False  # normal album: still capped


def test_uncapped_beats_a_limits_override():
    # Uncapped short-circuits ahead of get_limit, matching the serializer's `None` cap —
    # the two must never disagree about whether an album is full.
    policy = DefaultPolicy(
        max_per_album=3,
        uncapped_albums=frozenset({"__non_album__"}),
        get_limit=lambda fbid, default: 2,
    )
    assert policy.can_select("__non_album__", 99) is True
    assert policy.can_select("111", 2) is False  # capped album still honours the override

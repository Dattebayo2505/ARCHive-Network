from archivenetwork.selection.policy import DefaultPolicy


def test_cap_enforced_at_max():
    policy = DefaultPolicy(max_per_album=3)
    assert policy.can_select("111", 2) is True
    assert policy.can_select("111", 3) is False


def test_videos_are_selectable_and_uncapped():
    # Nothing is auto-kept: videos must be pickable, or the user could never ship them.
    policy = DefaultPolicy(max_per_album=3)
    assert policy.can_select("__videos__", 999) is True


def test_a_disregarded_album_is_never_selectable():
    """Non-album photos have no slot in the ready folder, so they may not be picked at all.

    Note the interaction with `uncapped`: `__non_album__` is *both*, and disregarded must
    win — otherwise the uncapped short-circuit would wave every pick through.
    """
    policy = DefaultPolicy(
        max_per_album=3,
        uncapped_albums=frozenset({"__non_album__"}),
        disregarded_albums=frozenset({"__non_album__"}),
    )
    assert policy.is_disregarded("__non_album__") is True
    assert policy.can_select("__non_album__", 0) is False
    assert policy.can_select("111", 0) is True  # ordinary albums are unaffected


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

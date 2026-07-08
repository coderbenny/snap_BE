def can_use_file_transfer(user) -> bool:
    """Return True if the user's active subscription includes file transfer.

    File transfer is bundled into every paid tier (pro, pro_ai, team).
    Free users (no subscription) do not have access.
    """
    sub = user.subscription
    return sub is not None and sub.status == 'active'

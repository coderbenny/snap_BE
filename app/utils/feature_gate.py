def can_use_file_transfer(user) -> bool:
    """Return True if the user's active subscription includes file transfer."""
    sub = user.subscription
    if sub is None or sub.status != 'active':
        return False
    if sub.tier == 'team':
        return True
    return bool(sub.file_transfer_addon)

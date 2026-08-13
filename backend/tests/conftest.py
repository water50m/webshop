import bcrypt

_real_gensalt = bcrypt.gensalt


def _fast_gensalt(rounds: int = 4, prefix: bytes = b"2b"):
    return _real_gensalt(rounds=4, prefix=prefix)


bcrypt.gensalt = _fast_gensalt

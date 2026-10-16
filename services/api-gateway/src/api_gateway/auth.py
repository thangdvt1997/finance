from __future__ import annotations

import hmac


def token_ok(supplied: str | None, tokens: tuple[str, ...], disabled: bool = False) -> bool:
    if disabled:
        return True
    if not supplied or not tokens:  # fail-closed khi chưa cấu hình token
        return False
    ok = False
    for t in tokens:  # so sánh hằng thời gian, không thoát sớm
        ok |= hmac.compare_digest(supplied.encode(), t.encode())
    return ok

"""PgRepo.bars: bộ nhớ khoảng lịch sử (tránh duyệt ~1900 chunk khi chuỗi ngắn). Không cần DB: thay `_q` bằng stub ghi lại tham số."""
from datetime import datetime, timedelta, timezone

from api_gateway.pg_repo import PgRepo

T0 = datetime(2024, 8, 18, tzinfo=timezone.utc)


def make(rows):
    repo = PgRepo.__new__(PgRepo)
    repo._span = {}          # tránh dùng chung trạng thái lớp giữa các test
    calls = []

    async def q(sql, *args):
        calls.append(args)
        return rows

    repo._q = q
    return repo, calls


async def test_short_series_sets_lower_bound_for_next_queries():
    rows = [{"ts_open": T0 + timedelta(hours=i)} for i in range(5, 0, -1)]      # 5 < limit 500 => đã thấy toàn bộ lịch sử
    repo, calls = make(rows)
    await repo.bars("EURUSD", "H1", None, None, "desc", 500, 0)
    assert calls[0][2] is None                                                    # lần đầu: không cận
    await repo.bars("EURUSD", "H1", None, None, "desc", 300, 0)
    assert calls[1][2] == min(r["ts_open"] for r in rows)                         # lần sau: cận dưới = nến cũ nhất đã biết
    await repo.bars("GBPUSD", "H1", None, None, "desc", 500, 0)
    assert calls[2][2] is None                                                    # chuỗi khác không bị ảnh hưởng


async def test_full_page_or_explicit_from_or_asc_do_not_set_bound():
    rows = [{"ts_open": T0 + timedelta(hours=i)} for i in range(3)]
    repo, calls = make(rows)
    await repo.bars("A", "H1", None, None, "desc", 3, 0)                          # đủ limit: có thể còn dữ liệu cũ hơn
    await repo.bars("A", "H1", None, None, "desc", 3, 0)
    assert calls[1][2] is None
    await repo.bars("B", "H1", T0, None, "desc", 500, 0)                          # `from` do client đặt: tôn trọng nguyên văn
    await repo.bars("B", "H1", None, None, "desc", 500, 0)
    assert calls[2][2] == T0 and calls[3][2] is None
    await repo.bars("C", "H1", None, None, "asc", 500, 0)
    await repo.bars("C", "H1", None, None, "asc", 500, 0)
    assert calls[5][2] is None
    await repo.bars("D", "H1", None, None, "desc", 500, 10)                      # offset>0: không suy ra cận
    await repo.bars("D", "H1", None, None, "desc", 500, 0)
    assert calls[7][2] is None


async def test_empty_result_sets_no_bound():
    repo, calls = make([])
    await repo.bars("X", "H1", None, None, "desc", 500, 0)
    await repo.bars("X", "H1", None, None, "desc", 500, 0)
    assert calls[1][2] is None

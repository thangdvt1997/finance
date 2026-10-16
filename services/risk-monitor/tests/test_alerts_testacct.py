import asyncio

from risk_monitor.alerts import AlertEmitter, is_test_account

ITEMS = [{"key": "dd", "label": "DD", "status": "crit", "value": 9.0, "unit": "%", "limit": 5}]


class FakeR:
    def __init__(self): self.h = {}
    async def hget(self, k, f): return self.h.get(f)
    async def hset(self, k, f, v): self.h[f] = v


class FakeBus:
    def __init__(self): self.sent = []
    async def publish(self, s, e): self.sent.append((s, e))


def test_is_test_account():
    assert is_test_account("mt5:99000123") and is_test_account("qa-x")
    assert not is_test_account("mt5:100000001") and not is_test_account("mt5:12345678")


def test_test_account_no_alert_real_account_alerts():
    bus = FakeBus(); em = AlertEmitter(FakeR(), bus, {})
    assert asyncio.run(em.process("mt5:99000555", ITEMS)) == 0 and not bus.sent
    assert asyncio.run(em.process("mt5:100000001", ITEMS)) == 1 and bus.sent

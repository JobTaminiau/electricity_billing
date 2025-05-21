from pathlib import Path
from coned_billing.loader import load_rate


def test_loader_roundtrip():
    rs = load_rate(Path("../tariffs/sc9_general_rate_1_LT.yml"))
    assert rs.code.startswith("SC")
    assert rs.customer_charge > 0
    assert rs.energy_components               # at least one energy block

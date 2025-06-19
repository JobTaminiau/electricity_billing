from pathlib import Path
from coned_billing.loader import load_rate
import coned_billing

TAR_DIR = Path(coned_billing.__file__).parent / "tariffs"


def test_loader_roundtrip():
    rs = load_rate(Path(TAR_DIR / "sc9_general_rate_1_LT.yml"))
    assert rs.code.startswith("SC")
    assert rs.customer_charge > 0
    assert rs.energy_components               # at least one energy block

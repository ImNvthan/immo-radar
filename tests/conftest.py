import sys
from pathlib import Path

import pandas as pd
import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from immo import analyse  # noqa: E402

DVF_CSV = Path(__file__).parent / "data" / "dvf_synthetique.csv"


@pytest.fixture(scope="session")
def dvf_brut():
    return pd.read_csv(DVF_CSV, dtype=str)


@pytest.fixture(scope="session")
def ventes(dvf_brut):
    return analyse.clean(dvf_brut)


@pytest.fixture
def cfg():
    return analyse.normaliser_config({"min_ventes": 5})


@pytest.fixture
def loyers(cfg):
    return analyse.Loyers(cfg["loyer_m2_defaut"], {})


@pytest.fixture
def ref(ventes):
    return ventes["date"].max()


@pytest.fixture
def stats(ventes, ref, loyers):
    return analyse.market_stats(ventes, ref, 5, loyers)

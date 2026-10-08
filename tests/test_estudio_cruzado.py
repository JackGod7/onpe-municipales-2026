import pandas as pd

import estudio_cruzado as e


def test_ultimo_digito_uniforme_no_se_aparta():
    valores = pd.Series(list(range(10, 210)))  # 20 de cada último dígito
    chi2, raro = e.ultimo_digito(valores)
    assert chi2 == 0 and not raro


def test_ultimo_digito_sesgado_se_aparta():
    chi2, raro = e.ultimo_digito(pd.Series([10, 20, 30, 40, 50] * 40))
    assert raro and chi2 > e.CRITICO_CHI2_9GL


def test_z_robusto_marca_el_atipico():
    z = e.z_robusto(pd.Series([0.1, -0.2, 0.0, 0.3, -0.1, 0.2, 15.0]))
    assert z.abs().idxmax() == 6 and z.iloc[6] > 3.5

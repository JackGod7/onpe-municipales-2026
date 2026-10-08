import json

import pandas as pd

import analisis


def _acta(i, elec, validos, emitidos, habiles=300, asistentes=None, **esp):
    base = {"id": i, "eleccion": elec, "distrito": "D", "mesa": f"M{i % 10}", "local": "L", "estado": "C",
            "habiles": habiles, "emitidos": emitidos, "validos": validos,
            "asistentes": emitidos if asistentes is None else asistentes,
            "nulos": 0, "blancos": 0, "impugnados": 0, "tiene_pdf": None}
    return {**base, **esp}


def test_aritmetica_detecta_suma_que_no_cuadra():
    a = pd.DataFrame([_acta(1, 4, 100, 100), _acta(2, 4, 100, 100)])
    v = pd.DataFrame([{"id": 1, "org": "A", "votos": 100}, {"id": 2, "org": "A", "votos": 90}])
    r = analisis.aritmetica(a, v)
    assert list(r["id"]) == [2]


def test_aritmetica_mas_votantes_que_habiles():
    a = pd.DataFrame([_acta(1, 4, 100, 100, habiles=80)])
    v = pd.DataFrame([{"id": 1, "org": "A", "votos": 100}])
    assert len(analisis.aritmetica(a, v)) == 1


def test_avisos_org_95pct_y_asistentes():
    a = pd.DataFrame([_acta(1, 4, 100, 100), _acta(2, 4, 100, 100, asistentes=90), _acta(3, 4, 100, 100)])
    v = pd.DataFrame([
        {"id": 1, "org": "A", "votos": 96}, {"id": 1, "org": "B", "votos": 4},
        {"id": 2, "org": "A", "votos": 50}, {"id": 2, "org": "B", "votos": 50},
        {"id": 3, "org": "A", "votos": 50}, {"id": 3, "org": "B", "votos": 50},
    ])
    r = analisis.avisos(a, v)
    assert set(r["id"]) == {1, 2}


def test_ranking_ordena_por_porcentaje():
    a = pd.DataFrame([_acta(1, 4, 100, 100), _acta(2, 4, 200, 200)])
    v = pd.DataFrame([{"id": 1, "org": "A", "votos": 10}, {"id": 2, "org": "A", "votos": 100}])
    r = analisis.ranking(a, v, "A")
    assert list(r["votos"]) == [100, 10]


def test_voto_cruzado_brecha_provincial_menos_distrital():
    filas, votos = [], []
    for m in range(1, 8):
        prov, dist = 60 + m % 3, 60  # brecha pequeña y variable en las mesas normales
        if m == 7:
            prov = 140  # mesa 7: mucho más en provincial que en distrital
        filas += [_acta(m * 10 + 3, 3, 150, 150, mesa=str(m)), _acta(m * 10 + 4, 4, 150, 150, mesa=str(m))]
        votos += [{"id": m * 10 + 3, "org": "A", "votos": prov}, {"id": m * 10 + 4, "org": "A", "votos": dist}]
    r = analisis.voto_cruzado(pd.DataFrame(filas), pd.DataFrame(votos), "A")
    assert r.iloc[0]["mesa"] == "7"
    assert r.iloc[0]["brecha"] > 50


def test_cuadre_compara_suma_de_mesas_con_total_oficial(tmp_path, monkeypatch):
    oficial = {"participantes": {"data": [{"nombreAgrupacionPolitica": "A", "nombreCandidato": "X", "totalVotosValidos": 100}]}}
    (tmp_path / "totales_140126_4.json").write_text(json.dumps(oficial))
    monkeypatch.setattr(analisis, "RAW", tmp_path)
    a = pd.DataFrame([{**_acta(1, 4, 60, 60), "ubigeo": 140126}, {**_acta(2, 4, 30, 30), "ubigeo": 140126}])
    v = pd.DataFrame([{"id": 1, "org": "A", "votos": 60}, {"id": 2, "org": "A", "votos": 30}])
    r = analisis.cuadre(a, v)
    assert r.iloc[0]["suma_mesas_contabilizadas"] == 90 and r.iloc[0]["dif"] == 10


def test_cuadre_separa_actas_no_contabilizadas(tmp_path, monkeypatch):
    oficial = {"participantes": {"data": [{"nombreAgrupacionPolitica": "A", "nombreCandidato": "X", "totalVotosValidos": 60}]}}
    (tmp_path / "totales_140126_4.json").write_text(json.dumps(oficial))
    monkeypatch.setattr(analisis, "RAW", tmp_path)
    a = pd.DataFrame([{**_acta(1, 4, 60, 60), "ubigeo": 140126}, {**_acta(2, 4, 0, 0), "ubigeo": 140126, "estado": "E"}])
    v = pd.DataFrame([{"id": 1, "org": "A", "votos": 60}, {"id": 2, "org": "A", "votos": 25}])
    r = analisis.cuadre(a, v).iloc[0]
    assert r["dif"] == 0 and r["votos_en_actas_no_contabilizadas"] == 25 and r["mesas_no_contabilizadas"] == 1


def test_cargar_clientes_sin_archivo_devuelve_vacio(tmp_path):
    assert analisis.cargar_clientes(tmp_path / "no_existe.json") == {}


def test_cargar_clientes_lee_organizacion_y_distrito(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"X Y": {"organizacion": "ORG", "distrito": "D"}}))
    assert analisis.cargar_clientes(f) == {"X Y": ("ORG", "D")}


def test_jee_distrital_lista_actas_no_contabilizadas(tmp_path, monkeypatch):
    def acta(mesa, estado, a, b):
        return {"idEleccion": 4, "codigoMesa": mesa, "codigoEstadoActa": estado, "nombreLocalVotacion": "L", "totalElectoresHabiles": 300,
                "detalle": [{"adDescripcion": "RENOVACIÓN POPULAR PERÚ", "adVotos": a},
                            {"adDescripcion": "PARTIDO DEMOCRÁTICO SOMOS PERÚ", "adVotos": b},
                            {"adDescripcion": "VOTOS NULOS", "adVotos": 9}],
                "lineaTiempo": [{"codigoEstadoActa": "E", "descripcionEstadoActaResolucion": "Acta con error aritmético"}]}
    linea = {"mesa": "1", "ubigeo": 240106, "data": [acta("1", "E", 40, 55), acta("2", "C", 1, 1)]}
    (tmp_path / "mesas.jsonl").write_text(json.dumps(linea) + "\n")
    monkeypatch.setattr(analisis, "RAW", tmp_path)
    r = analisis.jee_distrital()
    assert len(r) == 1
    assert (r.iloc[0]["votos_a"], r.iloc[0]["votos_b"], r.iloc[0]["votos_organizaciones"]) == (40, 55, 95)
    assert r.iloc[0]["motivo_jee"] == "Acta con error aritmético"

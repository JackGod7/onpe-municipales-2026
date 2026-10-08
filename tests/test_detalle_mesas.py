import json

import detalle_mesas


def test_pendientes_omite_mesas_ya_descargadas(tmp_path, monkeypatch):
    raw = tmp_path
    (raw / "actas_140126.json").write_text(json.dumps([{"codigoMesa": "000001"}, {"codigoMesa": "000002"}]))
    (raw / "actas_240106.json").write_text(json.dumps([{"codigoMesa": "000003"}]))
    (raw / "mesas.jsonl").write_text(json.dumps({"mesa": "000001", "ubigeo": 140126, "data": []}) + "\n")
    monkeypatch.setattr(detalle_mesas, "RAW", raw)
    monkeypatch.setattr(detalle_mesas, "OUT", raw / "mesas.jsonl")
    assert detalle_mesas.pendientes() == [("000003", 240106), ("000002", 140126)]


def test_espera_reto_escalona_y_termina():
    assert detalle_mesas.espera_reto(1) == 30
    assert detalle_mesas.espera_reto(25) == 120
    assert detalle_mesas.espera_reto(60) == 300
    assert detalle_mesas.espera_reto(500) is None


def test_prioridad_pdfs_no_contabilizadas_primero():
    import descargar_pdfs as d

    def a(ub, el, est, mesa):
        return {"idUbigeo": ub, "idEleccion": el, "codigoEstadoActa": est, "codigoMesa": mesa}

    ordenadas = sorted(
        [a(140126, 4, "C", "1"), a(240106, 4, "C", "2"), a(140126, 3, "E", "3"), a(240106, 4, "E", "4")], key=d.prioridad
    )
    assert [x["codigoMesa"] for x in ordenadas] == ["4", "3", "2", "1"]

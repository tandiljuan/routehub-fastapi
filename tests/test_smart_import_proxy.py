"""Smart Import proxy must forward every parameter the upstream service accepts.

An earlier proxy revision dropped depot_* on geocode, so internal queries
arrived without city context and bare streets failed to resolve. Mapping,
preview, and delete were also missing even though upstream advertises them
in ``next_actions``.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("RDBMS_URL", "sqlite://")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# Import model modules so every table is registered on SQLModel.metadata.
import models.company  # noqa: F401
import models.tenant  # noqa: F401
from models.smart_import_job import SmartImportJob

from libs.authorization.authorization import authorization
from models.database import get_session
from routes import smart_imports

#: Job ids the tests below address, all owned by company 1.
OWNED_JOBS = [f"imp_{n}" for n in range(1, 9)]


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _client(company_id: int = 1, owned: dict[str, int] | None = None) -> TestClient:
    """Minimal app with only this router, wired to an in-memory workspace.

    `owned` maps job_id → owning company. Default: every OWNED_JOBS id belongs
    to company 1, so the forwarding tests below run as that workspace.
    """
    session = _session()
    rows = owned if owned is not None else {j: 1 for j in OWNED_JOBS}
    for job_id, dueno in rows.items():
        session.add(SmartImportJob(job_id=job_id, company_id=dueno, filename="x.csv"))
    session.commit()

    app = FastAPI()
    app.include_router(smart_imports.router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[authorization] = lambda: company_id
    client = TestClient(app)
    client.session = session          # para inspeccionar filas en los tests
    return client


def _upstream_response(payload, status=200):
    res = MagicMock()
    res.status_code = status
    res.json.return_value = payload
    res.headers = {"content-type": "application/json"}
    res.content = b"{}"
    res.text = "{}"
    return res


class TestGeocodeForwarding(unittest.TestCase):
    """Depot context the UI already sends must not be dropped here."""

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_forwards_depot_context(self, http_client):
        post = http_client.return_value.__enter__.return_value.post
        post.return_value = _upstream_response({"job_id": "imp_1", "status": "geocode_queued"})

        r = _client().post("/imports/smart/imp_1/geocode", params={
            "origin_lat": -34.6037, "origin_lon": -58.3816,
            "depot_city": "CABA", "depot_region": "Buenos Aires",
            "depot_postcode": "C1000", "depot_country": "AR",
            "depot_address": "Av. Corrientes 1234",
            "max_distance_km": 80,
        })

        self.assertEqual(r.status_code, 202)
        params = post.call_args.kwargs["params"]
        self.assertEqual(params["depot_city"], "CABA")
        self.assertEqual(params["depot_region"], "Buenos Aires")
        self.assertEqual(params["depot_postcode"], "C1000")
        self.assertEqual(params["depot_country"], "AR")
        self.assertEqual(params["depot_address"], "Av. Corrientes 1234")
        self.assertEqual(params["max_distance_km"], 80)

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_forwards_enhance_addresses(self, http_client):
        post = http_client.return_value.__enter__.return_value.post
        post.return_value = _upstream_response({"job_id": "imp_1"})

        _client().post("/imports/smart/imp_1/geocode", params={
            "origin_lat": -34.6, "origin_lon": -58.4, "enhance_addresses": "true"})

        self.assertEqual(post.call_args.kwargs["params"]["enhance_addresses"], "true")

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_omits_absent_params(self, http_client):
        """None must not become the string 'None' upstream."""
        post = http_client.return_value.__enter__.return_value.post
        post.return_value = _upstream_response({"job_id": "imp_1"})

        _client().post("/imports/smart/imp_1/geocode",
                       params={"origin_lat": -34.6, "origin_lon": -58.4})

        params = post.call_args.kwargs["params"]
        self.assertNotIn("depot_city", params)
        self.assertNotIn("enhance_addresses", params)
        self.assertNotIn("bbox", params)


class TestCreateForwarding(unittest.TestCase):
    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "AsyncClient")
    def test_forwards_timezone_and_depot(self, http_client):
        post = http_client.return_value.__aenter__.return_value.post
        post.return_value = _upstream_response({"job_id": "imp_2", "status": "normalized"})

        r = _client().post(
            "/imports/smart",
            params={"timezone": "America/Argentina/Buenos_Aires",
                    "service_date": "2026-09-10",
                    "depot_city": "CABA", "depot_country": "AR",
                    "phone_region": "AR"},
            files={"file": ("entregas.csv", b"address\nAv. Corrientes 100\n", "text/csv")},
        )

        self.assertEqual(r.status_code, 201)
        params = post.call_args.kwargs["params"]
        self.assertEqual(params["timezone"], "America/Argentina/Buenos_Aires")
        self.assertEqual(params["service_date"], "2026-09-10")
        self.assertEqual(params["depot_city"], "CABA")
        self.assertEqual(params["depot_country"], "AR")

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "AsyncClient")
    def test_rejects_unsupported_extension_without_upstream_call(self, http_client):
        r = _client().post("/imports/smart",
                           files={"file": ("virus.exe", b"MZ", "application/octet-stream")})

        self.assertEqual(r.status_code, 415)
        http_client.return_value.__aenter__.return_value.post.assert_not_called()

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports, "MAX_UPLOAD_MB", 0.0001)
    @patch.object(smart_imports.httpx, "AsyncClient")
    def test_rejects_oversized_upload_without_upstream_call(self, http_client):
        r = _client().post("/imports/smart",
                           files={"file": ("big.csv", b"a,b\n" + b"1,2\n" * 5000, "text/csv")})

        self.assertEqual(r.status_code, 413)
        http_client.return_value.__aenter__.return_value.post.assert_not_called()


class TestLinkRewriting(unittest.TestCase):
    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_hrefs_point_at_proxy_not_upstream(self, http_client):
        http_client.return_value.__enter__.return_value.get.return_value = _upstream_response({
            "job_id": "imp_3",
            "urls": {"self": "/imports/imp_3",
                     "download_flat": "/imports/imp_3/download?format=flat"},
            "next_actions": [
                {"action": "download", "href": "/imports/imp_3/download?format=flat"},
                {"action": "geocode", "href": "/imports/imp_3/geocode"},
            ],
        })

        body = _client().get("/imports/smart/imp_3").json()

        self.assertEqual(body["urls"]["self"], "/imports/smart/imp_3")
        self.assertEqual(body["urls"]["download_flat"],
                         "/imports/smart/imp_3/download?format=flat")
        hrefs = [a["href"] for a in body["next_actions"]]
        self.assertEqual(hrefs, ["/imports/smart/imp_3/download?format=flat",
                                 "/imports/smart/imp_3/geocode"])


class TestMissingRoutes(unittest.TestCase):
    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_confirm_mapping(self, http_client):
        put = http_client.return_value.__enter__.return_value.put
        put.return_value = _upstream_response({"job_id": "imp_4", "status": "normalized"})

        r = _client().put("/imports/smart/imp_4/mapping",
                          json={"Dest.": "address", "Obs": None})

        self.assertEqual(r.status_code, 200)
        self.assertEqual(put.call_args.kwargs["json"], {"Dest.": "address", "Obs": None})

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_preview(self, http_client):
        get = http_client.return_value.__enter__.return_value.get
        get.return_value = _upstream_response({"rows": [], "columns": []})

        r = _client().get("/imports/smart/imp_5/preview", params={"limit": 5})

        self.assertEqual(r.status_code, 200)
        self.assertEqual(get.call_args.kwargs["params"]["limit"], 5)

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_delete_job(self, http_client):
        delete = http_client.return_value.__enter__.return_value.delete
        delete.return_value = _upstream_response({}, status=204)

        self.assertEqual(_client().delete("/imports/smart/imp_6").status_code, 204)

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_download_accepts_normalized(self, http_client):
        get = http_client.return_value.__enter__.return_value.get
        get.return_value = _upstream_response({}, status=200)

        r = _client().get("/imports/smart/imp_7/download", params={"format": "normalized"})

        self.assertEqual(r.status_code, 200)
        self.assertEqual(get.call_args.kwargs["params"]["format"], "normalized")


class TestFeatureFlagOff(unittest.TestCase):
    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", False)
    def test_disabled_routes_return_404(self):
        client = _client()
        self.assertEqual(client.get("/imports/smart/imp_1").status_code, 404)
        self.assertEqual(client.delete("/imports/smart/imp_1").status_code, 404)
        self.assertEqual(
            client.put("/imports/smart/imp_1/mapping", json={}).status_code, 404)


if __name__ == "__main__":
    unittest.main()


class TestWorkspaceIsolation(unittest.TestCase):
    """Smart Import is workspace-blind: it serves any id it is handed.

    RouteHub is the only thing between one workspace and another's customer
    addresses and phone numbers. A job id is not a secret — it travels in URLs,
    logs and support tickets.
    """

    AJENO = {"imp_otro": 2}          # job de la company 2

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_no_se_puede_leer_el_job_de_otro_workspace(self, http_client):
        r = _client(company_id=1, owned=self.AJENO).get("/imports/smart/imp_otro")

        self.assertEqual(r.status_code, 404)
        # Ni siquiera se consulta upstream: la existencia tampoco se filtra.
        http_client.return_value.__enter__.return_value.get.assert_not_called()

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_un_job_ajeno_no_se_puede_descargar(self, http_client):
        r = _client(company_id=1, owned=self.AJENO).get(
            "/imports/smart/imp_otro/download", params={"format": "flat"})

        self.assertEqual(r.status_code, 404)
        http_client.return_value.__enter__.return_value.get.assert_not_called()

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_un_job_ajeno_no_se_puede_regeocodificar(self, http_client):
        r = _client(company_id=1, owned=self.AJENO).post(
            "/imports/smart/imp_otro/geocode",
            params={"origin_lat": -34.6, "origin_lon": -58.4})

        self.assertEqual(r.status_code, 404)
        http_client.return_value.__enter__.return_value.post.assert_not_called()

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_un_job_ajeno_no_se_puede_borrar(self, http_client):
        cliente = _client(company_id=1, owned=self.AJENO)

        self.assertEqual(cliente.delete("/imports/smart/imp_otro").status_code, 404)
        http_client.return_value.__enter__.return_value.delete.assert_not_called()
        # y sigue existiendo para su dueno
        self.assertIsNotNone(cliente.session.get(SmartImportJob, "imp_otro"))

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_todas_las_rutas_con_job_id_estan_protegidas(self, http_client):
        """Una ruta nueva sin la guarda es una fuga: que el test lo note."""
        cliente = _client(company_id=1, owned=self.AJENO)
        casos = [
            ("get", "/imports/smart/imp_otro", {}),
            ("get", "/imports/smart/imp_otro/progress", {}),
            ("get", "/imports/smart/imp_otro/issues", {}),
            ("get", "/imports/smart/imp_otro/preview", {}),
            ("get", "/imports/smart/imp_otro/download", {"params": {"format": "flat"}}),
            ("post", "/imports/smart/imp_otro/geocode",
             {"params": {"origin_lat": -34.6, "origin_lon": -58.4}}),
            ("put", "/imports/smart/imp_otro/mapping", {"json": {"A": "address"}}),
            ("delete", "/imports/smart/imp_otro", {}),
        ]
        for metodo, ruta, kwargs in casos:
            with self.subTest(ruta=f"{metodo.upper()} {ruta}"):
                r = getattr(cliente, metodo)(ruta, **kwargs)
                self.assertEqual(r.status_code, 404)

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_un_job_inexistente_responde_igual_que_uno_ajeno(self, http_client):
        """404 en ambos casos: la respuesta no distingue 'no existe' de 'no es tuyo'."""
        cliente = _client(company_id=1, owned={})

        self.assertEqual(cliente.get("/imports/smart/imp_fantasma").status_code, 404)


class TestOwnershipRecord(unittest.TestCase):
    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "AsyncClient")
    def test_el_import_queda_ligado_al_workspace_que_lo_creo(self, http_client):
        post = http_client.return_value.__aenter__.return_value.post
        post.return_value = _upstream_response({"job_id": "imp_nuevo", "status": "normalized"})

        cliente = _client(company_id=7, owned={})
        r = cliente.post("/imports/smart",
                         files={"file": ("entregas.csv", b"address\nX 1\n", "text/csv")})

        self.assertEqual(r.status_code, 201)
        fila = cliente.session.get(SmartImportJob, "imp_nuevo")
        self.assertIsNotNone(fila, "el job quedo sin dueno: nadie podria leerlo")
        self.assertEqual(fila.company_id, 7)
        self.assertEqual(fila.filename, "entregas.csv")

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_borrar_saca_la_fila_solo_si_upstream_confirmo(self, http_client):
        borrar = http_client.return_value.__enter__.return_value.delete
        borrar.return_value = _upstream_response({}, status=204)

        cliente = _client(company_id=1, owned={"imp_mio": 1})
        self.assertEqual(cliente.delete("/imports/smart/imp_mio").status_code, 204)
        self.assertIsNone(cliente.session.get(SmartImportJob, "imp_mio"))

    @patch.object(smart_imports, "SMART_IMPORT_ENABLED", True)
    @patch.object(smart_imports.httpx, "Client")
    def test_si_upstream_falla_la_fila_sobrevive(self, http_client):
        """Borrar la fila primero dejaria el job vivo y sin dueno: irrecuperable."""
        borrar = http_client.return_value.__enter__.return_value.delete
        borrar.return_value = _upstream_response({"detail": "boom"}, status=500)

        cliente = _client(company_id=1, owned={"imp_mio": 1})
        self.assertEqual(cliente.delete("/imports/smart/imp_mio").status_code, 500)
        self.assertIsNotNone(cliente.session.get(SmartImportJob, "imp_mio"))

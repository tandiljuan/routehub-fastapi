"""
Tests para graph_tag_for_company: parte de cliente del tag de grafos del optimizer,
derivada del alias de la company (email del usuario web) con fallback a C{id}.
"""
from libs.plan_build import graph_tag_for_company


def test_web_user_alias_uses_email_local_part():
    # Alias generado en el primer login: web-{email_local}-{uid8}
    assert graph_tag_for_company(7, "web-martinvizzolini-a1b2c3d4") == "MARTINVIZZOLINI"


def test_web_user_alias_with_hyphenated_email():
    # Email con punto → slug con guión interno; el sufijo uid igual se recorta
    assert graph_tag_for_company(7, "web-martin-vizzolini-a1b2c3d4") == "MARTINVIZZOLINI"


def test_plain_alias_is_normalized_whole():
    assert graph_tag_for_company(1, "vepathos-web-client") == "VEPATHOSWEBCLIENT"
    assert graph_tag_for_company(1, "mvizzolini") == "MVIZZOLINI"


def test_fallback_to_company_id_without_alias():
    assert graph_tag_for_company(12, None) == "C12"
    assert graph_tag_for_company(12, "") == "C12"
    # Alias que queda vacío tras normalizar (solo símbolos) también cae al fallback
    assert graph_tag_for_company(12, "!!!") == "C12"


def test_result_is_optimizer_filename_safe():
    # El parser de filenames del optimizer exige [A-Z0-9]+ en la parte de cliente
    import re
    for alias in ("web-martinvizzolini-a1b2c3d4", "Ñandú S.A.", "user@example.com", None):
        tag = graph_tag_for_company(3, alias)
        assert re.fullmatch(r"[A-Z0-9]+", tag), tag


def test_long_alias_is_truncated():
    tag = graph_tag_for_company(3, "a" * 100)
    assert len(tag) <= 24

import os
from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException
from sqlmodel import Session, SQLModel, select

from libs.authorization.authorization import authorization
from models.company import Company
from models.database import Session as DbSession
from models.tenant import Tenant

# Product tenant shared by vepathos-api-doc + vepathos-router-client (same auth stack).
DEFAULT_TENANT_ALIAS = "client-web"

TENANT_ALIAS = (
    os.environ.get("ROUTEHUB_TENANT_ALIAS", DEFAULT_TENANT_ALIAS).strip()
    or DEFAULT_TENANT_ALIAS
)

ScopedModel = TypeVar("ScopedModel", bound=SQLModel)


def get_product_tenant(db: DbSession) -> Tenant:
    """Resolve the deployment product tenant from DB (no inserts).

    Used when issuing API keys (CLI) to confirm a company belongs to this
    deployment. Request scoping comes from the API key, not from this lookup.
    """
    tenant = db.exec(select(Tenant).where(Tenant.alias == TENANT_ALIAS)).first()
    if tenant is None:
        raise HTTPException(
            status_code=503,
            detail=f"Tenant '{TENANT_ALIAS}' is not configured in the database",
        )
    return tenant


def get_company_for_tenant(db: DbSession, company_id: int, tenant_id: int) -> Company:
    """Resolve customer workspace (company) under the product tenant."""
    company = db.get(Company, company_id)
    if company is None or company.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def assert_company_match(resource, company_id: int, label: str = "Resource") -> None:
    if resource is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    if getattr(resource, "company_id", None) != company_id:
        raise HTTPException(status_code=404, detail=f"{label} not found")


def assert_related_company_id(
    db: Session,
    model: type[ScopedModel],
    resource_id: int | str,
    company_id: int,
    label: str,
) -> None:
    row = db.get(model, int(resource_id))
    assert_company_match(row, company_id, label)


def assert_related_company_ids(
    db: Session,
    model: type[ScopedModel],
    raw_ids: list[str],
    company_id: int,
    label: str,
) -> None:
    if not raw_ids:
        return
    ids = [int(i) for i in raw_ids]
    found = set(
        db.exec(
            select(model.id).where(
                model.id.in_(ids),
                model.company_id == company_id,
            )
        ).all()
    )
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"{label} not found for this workspace: {', '.join(missing)}",
        )


def assert_vehicle_ids_for_company(
    db: Session,
    raw_ids: list[str],
    company_id: int,
) -> None:
    from models.vehicle import Vehicle

    assert_related_company_ids(db, Vehicle, raw_ids, company_id, "Vehicle")


# Workspace scope = the company bound to the request's API key (auth + scope
# resolved together). FastAPI caches the dependency, so the lookup runs once.
CompanyDep = Annotated[int, Depends(authorization)]

import asyncio
from importlib.resources import path
import tempfile
import uuid
from fastapi import HTTPException
from sqlalchemy.orm import Session, defer, joinedload
from sqlalchemy import desc, func, or_, select
from typing import Optional, List, Dict, Tuple, Any
from app.models.sop import SOP, SOPDocument
from app.models.client import Client
from app.models.status import Status
from app.models.sop_provider_mapping import SopProviderMapping
from app.models.user import User
from app.models.organisation import Organisation
from app.models.user_client import UserClient
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from io import BytesIO
from app.services.ai_sop_service import AISOPService
class SOPService:

    @staticmethod
    def _get_org_id(current_user):
        org_id = getattr(current_user, "context_organisation_id", None) or getattr(current_user, "organisation_id", None)
        is_super = getattr(current_user, "context_is_superadmin", getattr(current_user, "is_superuser", False))

        # normal user must have org
        if not org_id and not is_super:
            raise HTTPException(403, "No organisation selected")

        return org_id
    @staticmethod
    def _base_visible_sops_query(db: Session):
        return db.query(SOP).join(Status, Status.id == SOP.status_id).filter(
            or_(
                Status.type == "GENERAL",
                Status.code.in_(["FAILED", "AI_FAILED"])
            )
        )

    @staticmethod
    def check_sop_exists(
        client_id: str,
        provider_ids: list[str] | None,
        db: Session,
        exclude_sop_id: str | None = None,
    ):
        if not client_id or not provider_ids:
            return False

        # get ACTIVE GENERAL status id
        active_status_id = db.query(Status.id).filter(
            Status.code == "ACTIVE",
            Status.type == "GENERAL"
        ).scalar()

        if not active_status_id:
            return False

        # normalize ids
        provider_ids = [str(pid) for pid in provider_ids]

        q = (
            db.query(SopProviderMapping.provider_id)
            .join(SOP, SOP.id == SopProviderMapping.sop_id)
            .filter(
                SOP.client_id == client_id,
                SOP.status_id == active_status_id,
                SopProviderMapping.provider_id.in_(provider_ids)
            )
        )

        if exclude_sop_id:
            q = q.filter(SOP.id != exclude_sop_id)

        return db.query(q.exists()).scalar()
    @staticmethod
    def get_sops(
        db: Session,
        current_user: Any,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        status_code: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        organisation_id: Optional[str] = None,
        created_by: Optional[str] = None,
        client_id: Optional[str] = None
    ) -> Tuple[List[SOP], int]:

        query = SOPService._base_visible_sops_query(db).options(
            defer(SOP.workflow_process),
            defer(SOP.billing_guidelines),
            defer(SOP.payer_guidelines),
            defer(SOP.coding_rules_cpt),
            defer(SOP.coding_rules_icd),
        )
        org_id = SOPService._get_org_id(current_user)

        if org_id:
            query = query.filter(SOP.organisation_id == org_id)

        # --- Additional Filters ---
        if status_code:
            status = db.query(Status).filter(
                Status.code == status_code,
                Status.type == "GENERAL"
            ).first()
            if status:
                query = query.filter(SOP.status_id == status.id)

        if from_date:
            query = query.filter(SOP.created_at >= from_date)
        if to_date:
            query = query.filter(SOP.created_at <= to_date)
        if organisation_id:
            org_ids = organisation_id.split(',')
            query = query.filter(SOP.organisation_id.in_(org_ids))
        if created_by:
            creator_ids = created_by.split(',')
            query = query.filter(SOP.created_by.in_(creator_ids))
        if client_id:
            cl_ids = client_id.split(',')
            query = query.filter(SOP.client_id.in_(cl_ids))

        if search:
            p = f"%{search}%"
            # Outer join to ensure we don't drop SOPs without clients but still can search client data
            query = query.outerjoin(Client, SOP.client_id == Client.id)
            query = query.filter(
                or_(
                    SOP.title.ilike(p),
                    SOP.category.ilike(p),
                    SOP.provider_info["providerName"].astext.ilike(p),
                    Client.business_name.ilike(p),
                    Client.npi.ilike(p),
                    Client.first_name.ilike(p),
                    Client.last_name.ilike(p)
                )
            )

        total = query.count()
        sops = query.order_by(desc(SOP.created_at)).offset(skip).limit(limit).options(
            joinedload(SOP.creator),
            joinedload(SOP.organisation),
            joinedload(SOP.client),
            joinedload(SOP.lifecycle_status),
            joinedload(SOP.documents)
        ).all()
        
        formatted_sops = [SOPService._format_sop(sop) for sop in sops]
        return formatted_sops, total
        
    @staticmethod
    def get_sop_stats(db: Session, current_user: Any) -> Dict[str, int]:
        """
        Visibility stats ONLY.
        workflow_status_id is intentionally ignored.
        """

        q = (
            db.query(
                func.count(SOP.id)
                    .filter(or_(Status.type == "GENERAL", Status.code.in_(["FAILED", "AI_FAILED"])))
                    .label("total"),
                func.count(SOP.id)
                    .filter(Status.code == "ACTIVE")
                    .label("active"),
                func.count(SOP.id)
                    .filter(Status.code == "INACTIVE")
                    .label("inactive"),
            )
            .select_from(SOP)
            .join(Status, Status.id == SOP.status_id)
            .filter(or_(Status.type == "GENERAL", Status.code.in_(["FAILED", "AI_FAILED"])))
        )
        org_id = SOPService._get_org_id(current_user)
        if org_id:
            q = q.filter(SOP.organisation_id == org_id)
        
        row = q.one()

        return {
            "total_sops": row.total,
            "active_sops": row.active,
            "inactive_sops": row.inactive,
        }

    @staticmethod
    def _format_sop(sop: SOP) -> Dict:
        """Helper to format SOP data with descriptive names."""
        from sqlalchemy.orm import attributes
        from app.services.s3_service import s3_service
        # Start with model attributes
        data = {
            "id": sop.id,
            "title": sop.title,
            "category": sop.category,
            "provider_type": sop.provider_type,
            "client_id": sop.client_id,
            "created_by": sop.created_by,
            "organisation_id": sop.organisation_id,
            "status_id": sop.status_id,
            "workflow_status_id": sop.workflow_status_id,
            "created_at": sop.created_at,
            "updated_at": sop.updated_at,
            "provider_info": sop.provider_info,
            "workflow_process": sop.workflow_process,
            "billing_guidelines": sop.billing_guidelines,
            "payer_guidelines": sop.payer_guidelines,
            "coding_rules": sop.coding_rules,
            "coding_rules_cpt": sop.coding_rules_cpt,
            "coding_rules_icd": sop.coding_rules_icd,
            "documents": [
                {
                    "id": str(doc.id),
                    "name": doc.name,
                    "category": doc.category,
                    "s3_key": doc.s3_key,
                    "document_url": s3_service.generate_presigned_url(
                        doc.s3_key,
                        response_content_disposition=f'inline; filename="{doc.name}"'
                    ),
                    "created_at": doc.created_at,
                    "extracted_data": doc.extracted_data,
                    "processed": doc.processed
                }
                for doc in sop.documents
            ] if sop.documents else [],
            "status": {
                "id": sop.lifecycle_status.id,
                "code": sop.lifecycle_status.code,
                "description": sop.lifecycle_status.description
            } if (sop.lifecycle_status and attributes.instance_state(sop).has_identity) else None
        }

        # Organisation Name
        data["organisation_name"] = sop.organisation.name if sop.organisation else None

        # CLIENT NAME (single source of truth)
        if sop.client:
            data["client_npi"] = sop.client.npi

            if sop.client.business_name:
                data["client_name"] = sop.client.business_name

            else:
                names = [
                    sop.client.first_name,
                    sop.client.middle_name,
                    sop.client.last_name
                ]
                data["client_name"] = " ".join([n for n in names if n]).strip()

        else:
            data["client_name"] = None
            data["client_npi"] = None
        # Created By Name
        if sop.creator:
            names = [sop.creator.first_name, sop.creator.middle_name, sop.creator.last_name]
            data["created_by_name"] = " ".join([n for n in names if n]).strip()

        elif sop.organisation:
            data["created_by_name"] = sop.organisation.name

        else:
            data["created_by_name"] = None
        # provider summary for list view
        data["provider_name"] = None

        if sop.provider_info:
            data["provider_name"] = sop.provider_info.get("providerName")
        return data
    @staticmethod
    def get_sop_by_id(sop_id: str, db: Session, current_user: User = None):
        org_id = SOPService._get_org_id(current_user)

        query = db.query(SOP).filter(SOP.id == sop_id)

        # if org context exists → lock to org
        if org_id:
            query = query.filter(SOP.organisation_id == org_id)

        sop = query.options(
            joinedload(SOP.creator),
            joinedload(SOP.organisation),
            joinedload(SOP.client),
            joinedload(SOP.lifecycle_status),
            joinedload(SOP.documents)
        ).first()

        if not sop:
            return None


        # 🔥 BACKWARD COMPAT FIX
        if sop.billing_guidelines and len(sop.billing_guidelines) > 0:
            first = sop.billing_guidelines[0]
            if isinstance(first, dict) and "title" in first and "rules" not in first:
                sop.billing_guidelines = SOPService.upgrade_flat_billing_guidelines(
                    sop.billing_guidelines
                )
        if sop.payer_guidelines:
            normalized = []

            for pg in sop.payer_guidelines:
                if not isinstance(pg, dict):
                    continue

                # NEW AI STRUCTURE
                if "payer_name" in pg:
                    normalized.append({
                        "payerName": pg.get("payer_name"),
                        "description": pg.get("description", "")
                    })

            sop.payer_guidelines = normalized    
        from app.models.provider import Provider
        from app.models.sop_provider_mapping import SopProviderMapping

        linked_providers = (
            db.query(Provider)
            .join(SopProviderMapping, SopProviderMapping.provider_id == Provider.id)
            .filter(SopProviderMapping.sop_id == sop.id)
            .all()
        )
        
        formatted_sop = SOPService._format_sop(sop)

        # Attach providers
        p_info = sop.provider_info or {}
        client_name = formatted_sop.get("client_name")
        client_npi = formatted_sop.get("client_npi")

        formatted_sop["providers"] = [
            {
                "id": str(p.id),
                "name": f"{p.first_name} {p.middle_name or ''} {p.last_name}".strip().replace("  ", " "),
                "first_name": p.first_name,
                "last_name": p.last_name,
                "npi": p.npi,
                "type": "Individual",
                "software": p_info.get("software", ""),
                "practiceName": client_name,
                "providerName": p_info.get("providerName", ""),
                "clearinghouse": p_info.get("clearinghouse", ""),
                "providerTaxID": p_info.get("providerTaxID", ""),
                "billingAddress": p_info.get("billingAddress", ""),
                "billingProviderNPI": p_info.get("billingProviderNPI", ""),
                "billingProviderName": p_info.get("billingProviderName", ""),
                "client_name": client_name,
                "client_npi": client_npi
            }
            for p in linked_providers
        ]
        return formatted_sop
    @staticmethod
    def get_blocked_providers(client_id, provider_ids, db, exclude_sop_id=None):

        active_status = db.query(Status).filter(
            Status.code == "ACTIVE",
            Status.type == "GENERAL"
        ).first()

        if not active_status:
            return []

        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return []
        if client.type == "Individual":

            q = db.query(SOP.id).filter(
                SOP.client_id == client_id,
                SOP.status_id == active_status.id
            )

            # 🔥 THIS IS THE MISSING PIECE
            if exclude_sop_id:
                q = q.filter(SOP.id != exclude_sop_id)

            exists = db.query(q.exists()).scalar()

            if exists:
                return ["CLIENT_BLOCKED"]

            return []

        if not provider_ids:
            return []

        q = (
            db.query(SopProviderMapping.provider_id)
            .join(SOP, SOP.id == SopProviderMapping.sop_id)
            .filter(
                SOP.client_id == client_id,
                SOP.status_id == active_status.id,
                SopProviderMapping.provider_id.in_(provider_ids)
            )
        )

        # 🔥 ALSO EXCLUDE CURRENT SOP HERE
        if exclude_sop_id:
            q = q.filter(SOP.id != exclude_sop_id)

        return [r.provider_id for r in q.all()]
    @staticmethod
    def create_sop(sop_data: Dict, db: Session, current_user: Any, client_id: str) -> SOP:

        provider_ids = sop_data.pop("provider_ids", [])

        org_id = SOPService._get_org_id(current_user)

        sop_data["organisation_id"] = org_id
        sop_data["created_by"] = str(current_user.id)

        if not sop_data.get("status_id"):
            active = db.query(Status).filter(
                Status.code == "ACTIVE",
                Status.type == "GENERAL"
            ).first()
            sop_data["status_id"] = active.id

        # 🔥 VALIDATE BEFORE INSERTING ANYTHING
        if SOPService.check_sop_exists(client_id, provider_ids, db):
            raise HTTPException(
                400,
                "One or more selected providers already have an active SOP for this client."
            )

        # 🔥 Create SOP FIRST
        db_sop = SOP(**sop_data)
        db.add(db_sop)
        db.commit()
        db.refresh(db_sop)

        # 🔥 THEN INSERT MAPPINGS
        if provider_ids:
            for pid in provider_ids:
                db.add(SopProviderMapping(
                    sop_id=db_sop.id,
                    provider_id=pid,
                    created_by=str(current_user.id)
                ))
            db.commit()

        return db_sop
    @staticmethod
    def process_extra_document(
        document_id,
        sop_id,
        file_content,
        content_type,
        category
    ):

        from app.core.database import SessionLocal

        db = SessionLocal()

        try:

            # temp file
            suffix = ".tmp"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(file_content)
                path = tmp.name

            text = asyncio.run(
                AISOPService.extract_text(path, content_type)
            )

            structured = asyncio.run(
                AISOPService.ai_extract_sop_structured(text)
            )

            doc = db.query(SOPDocument).filter(SOPDocument.id == document_id).first()
            sop = db.query(SOP).filter(SOP.id == sop_id).first()

            if not doc or not sop:
                return

            # store extracted result
            doc.extracted_data = structured

            # apply based on category
            if category == "Workflow Process":
                sop.workflow_process = structured.get("workflow_process")

            elif category == "Billing Guidelines":
                sop.billing_guidelines = structured.get("billing_guidelines")

            elif category == "Posting Charges Rules":
                wf = sop.workflow_process or {}
                wf["posting_charges_rules"] = structured.get("workflow_process", {}).get("posting_charges_rules")
                sop.workflow_process = wf

            db.commit()

        except Exception as e:
            print("Extra doc extraction failed:", e)

        finally:
            db.close()
    @staticmethod
    def apply_extraction_to_sop(sop, category, extracted):

        if category == "Workflow Process":
            sop.workflow_process = extracted.get("workflow_process")

        elif category == "Posting Charges Rules":
            wf = sop.workflow_process or {}
            wf["posting_charges_rules"] = extracted.get("workflow_process", {}).get(
                "posting_charges_rules"
            )
            sop.workflow_process = wf

        elif category == "Eligibility Verification Portals":
            wf = sop.workflow_process or {}
            wf["eligibility_verification_portals"] = extracted.get(
                "workflow_process", {}
            ).get("eligibility_verification_portals")
            sop.workflow_process = wf

        elif category == "Payer Guidelines":

            extracted_rules = extracted.get("payer_guidelines", [])

            if not extracted_rules:
                return

            existing = sop.payer_guidelines or []

            existing_titles = {r.get("title") for r in existing}

            for rule in extracted_rules:
                if rule.get("title") not in existing_titles:
                    existing.append(rule)

            sop.payer_guidelines = existing
        elif category == "Coding Guidelines":

            # CPT
            cpt = extracted.get("coding_rules_cpt", [])
            if cpt:
                existing = sop.coding_rules_cpt or []
                existing.extend(cpt)
                sop.coding_rules_cpt = existing

            # ICD
            icd = extracted.get("coding_rules_icd", [])
            if icd:
                existing = sop.coding_rules_icd or []
                existing.extend(icd)
                sop.coding_rules_icd = existing
    @staticmethod
    def extract_from_document(doc):

        from app.services.s3_service import s3_service
        import tempfile
        import os

        file_data = asyncio.run(s3_service.download_file(doc.s3_key))

        ext = os.path.splitext(doc.name)[1]

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(file_data)
            path = tmp.name

        text = asyncio.run(AISOPService.extract_text(path))

        structured = asyncio.run(
            AISOPService.ai_extract_sop_structured(text)
        )

        return structured
    @staticmethod
    def update_sop(sop_id: str, sop_data: Dict, db: Session, current_user: User):
        org_id = SOPService._get_org_id(current_user)

        db_sop = db.query(SOP).filter(
            SOP.id == sop_id,
            SOP.organisation_id == org_id
        ).first()
        if not db_sop:
            return None

        provider_ids = sop_data.get("provider_ids")

        if provider_ids is None:
            provider_ids = [
                str(m.provider_id)
                for m in db.query(SopProviderMapping)
                .filter(SopProviderMapping.sop_id == sop_id)
                .all()
            ]

        if SOPService.check_sop_exists(
            client_id=db_sop.client_id,
            provider_ids=provider_ids,
            db=db,
            exclude_sop_id=sop_id,
        ):
            raise HTTPException(400, "Provider already has active SOP")

        if "provider_ids" in sop_data:
            new_ids = set(provider_ids)
            existing = db.query(SopProviderMapping).filter(
                SopProviderMapping.sop_id == sop_id
            ).all()
            existing_ids = {str(m.provider_id) for m in existing}

            to_add = new_ids - existing_ids
            to_remove = existing_ids - new_ids

            if to_remove:
                db.query(SopProviderMapping).filter(
                    SopProviderMapping.sop_id == sop_id,
                    SopProviderMapping.provider_id.in_(to_remove)
                ).delete(synchronize_session=False)

            for pid in to_add:
                db.add(SopProviderMapping(sop_id=sop_id, provider_id=pid))

        allowed_fields = {
            "title",
            "category",
            "provider_type",
            "client_id",
            "provider_info",
            "workflow_process",
            "billing_guidelines",
            "payer_guidelines",
            "coding_rules_cpt",
            "coding_rules_icd",
            "status_id",
        }

        for k, v in sop_data.items():
            if k == "provider_ids":
                continue
            if k not in allowed_fields:
                continue

            if k == "workflow_process" and isinstance(v, dict):
                existing = db_sop.workflow_process or {}
                existing.update(v)
                setattr(db_sop, "workflow_process", existing)
            else:
                setattr(db_sop, k, v)

        db.commit()
        db.refresh(db_sop)

        return SOPService.get_sop_by_id(sop_id, db, current_user)
    @staticmethod
    def delete_sop(sop_id: str, db: Session, current_user: User = None) -> bool:
        
        org_id = SOPService._get_org_id(current_user)

        query = db.query(SOP).filter(SOP.id == sop_id)
        if org_id:
            query = query.filter(SOP.organisation_id == org_id)

        db_sop = query.first()
        if not db_sop:
            return False
        
        # 1. Clear provider mappings to avoid ForeignKeyViolation
        db.query(SopProviderMapping).filter(SopProviderMapping.sop_id == sop_id).delete()
        
        # 2. Finally delete the SOP
        db.delete(db_sop)
        db.commit()
        return True
    @staticmethod
    def upgrade_flat_billing_guidelines(flat: list[dict]) -> list[dict]:
        """
        Converts OLD flat billing_guidelines into NEW grouped format.
        """
        grouped: dict[str, list[dict]] = {}

        for item in flat:
            if not isinstance(item, dict):
                continue

            title = item.get("title", "Guidelines").strip()
            desc = item.get("description", "").strip()

            if not desc:
                continue

            grouped.setdefault(title, []).append({
                "description": desc
            })

        return [
            {
                "category": category,
                "rules": rules
            }
            for category, rules in grouped.items()
        ]
    
    @staticmethod
    def _build_coding_table(
    story,
    title: str,
    headers: list[str],
    rows: list[dict],
    field_map: list[str],
    styles,
    colors_cfg,
):
        if not rows:
            return

        story.append(Paragraph(title, styles["section_header"]))

        header_row = [
            Paragraph(f"<b>{h}</b>", styles["th"]) for h in headers
        ]
        table_data = [header_row]

        for r in rows:
            table_data.append([
                Paragraph(str(r.get(f, "") or ""), styles["td"])
                for f in field_map
            ])

        table = Table(table_data, repeatRows=1)
        table.setStyle(colors_cfg)
        story.append(table)
        story.append(Spacer(1, 0.2 * inch))

    @staticmethod
    def generate_sop_pdf(sop: Any) -> bytes:
        if not isinstance(sop, dict):
            sop = SOPService._format_sop(sop)

        import copy
        sop = copy.deepcopy(sop)  # don't mutate the caller's dict

        for doc in sop.get("documents", []):
            if not doc.get("processed") or not doc.get("extracted_data"):
                continue

            extracted = doc["extracted_data"]
            category  = doc.get("category", "")

            # Billing Guidelines
            if "billing_guidelines" in extracted and extracted["billing_guidelines"]:
                existing = sop.get("billing_guidelines") or []
                incoming = extracted["billing_guidelines"]
                existing_categories = {g.get("category") for g in existing if isinstance(g, dict)}
                for g in incoming:
                    if isinstance(g, dict) and g.get("category") not in existing_categories:
                        existing.append(g)
                        existing_categories.add(g.get("category"))
                sop["billing_guidelines"] = existing

            # Payer Guidelines
            if "payer_guidelines" in extracted and extracted["payer_guidelines"]:
                existing = sop.get("payer_guidelines") or []
                incoming = extracted["payer_guidelines"]
                existing_titles = {p.get("title") or p.get("payerName") for p in existing if isinstance(p, dict)}
                for p in incoming:
                    if isinstance(p, dict):
                        key = p.get("title") or p.get("payerName") or p.get("payer_name")
                        if key not in existing_titles:
                            existing.append(p)
                            existing_titles.add(key)
                sop["payer_guidelines"] = existing

            # CPT Coding Rules
            if "coding_rules_cpt" in extracted and extracted["coding_rules_cpt"]:
                existing = sop.get("coding_rules_cpt") or []
                incoming = extracted["coding_rules_cpt"]
                existing_codes = {r.get("cptCode") for r in existing if isinstance(r, dict)}
                for r in incoming:
                    if isinstance(r, dict) and r.get("cptCode") not in existing_codes:
                        existing.append(r)
                        existing_codes.add(r.get("cptCode"))
                sop["coding_rules_cpt"] = existing

            # ICD Coding Rules
            if "coding_rules_icd" in extracted and extracted["coding_rules_icd"]:
                existing = sop.get("coding_rules_icd") or []
                incoming = extracted["coding_rules_icd"]
                existing_codes = {r.get("icdCode") for r in existing if isinstance(r, dict)}
                for r in incoming:
                    if isinstance(r, dict) and r.get("icdCode") not in existing_codes:
                        existing.append(r)
                        existing_codes.add(r.get("icdCode"))
                sop["coding_rules_icd"] = existing

            # Workflow Process (merge sub-keys, don't overwrite base description)
            if "workflow_process" in extracted and extracted["workflow_process"]:
                incoming_wf = extracted["workflow_process"]
                existing_wf = dict(sop.get("workflow_process") or {})
                for k, v in incoming_wf.items():
                    if k == "description":
                        # Never overwrite the main SOP description from a doc
                        continue
                    if isinstance(v, list):
                        existing_list = existing_wf.get(k) or []
                        combined = list(existing_list)
                        existing_set = set(combined)
                        for item in v:
                            if item not in existing_set:
                                combined.append(item)
                                existing_set.add(item)
                        existing_wf[k] = combined
                    elif v and not existing_wf.get(k):
                        existing_wf[k] = v
                sop["workflow_process"] = existing_wf
        # ── End extracted_data merge ──────────────────────────────────────────

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.75*inch, rightMargin=0.75*inch)
        styles = getSampleStyleSheet()
        story = []

        primary_color = colors.HexColor('#0c4a6e')
        accent_color  = colors.HexColor('#0ea5e9')
        header_bg     = colors.HexColor('#e0f2fe')
        text_color    = colors.HexColor('#334155')
        label_color   = colors.HexColor('#64748b')
        bs = styles['BodyText']

        cat_style      = ParagraphStyle('Category', parent=bs, fontSize=11, textColor=accent_color, spaceAfter=6, alignment=1)
        section_header = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=14, textColor=primary_color, spaceBefore=12, spaceAfter=6, borderPadding=4)

        pdf_styles = {
            "section_header": section_header,
            "th": ParagraphStyle('TH', parent=bs, textColor=primary_color, alignment=1, fontSize=10, fontName='Helvetica-Bold'),
            "td": ParagraphStyle('TD', parent=bs, textColor=text_color, fontSize=9),
        }

        table_styles = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), header_bg),
            ('LINEBELOW', (0,0), (-1,0), 1, accent_color),
            ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 6),
        ])

        def mk_field(label, value):
            return Paragraph(f"<font color='{label_color.hexval()}'><b>{label}</b></font><br/><font color='{text_color.hexval()}'>{value or '-'}</font>", bs)

        title_style = ParagraphStyle('MainTitle', parent=styles['Title'], fontSize=24, textColor=primary_color, spaceAfter=8, leading=28)
        story.append(Paragraph(sop.get('title', 'SOP'), title_style))
        story.append(Paragraph(f"{sop.get('category', '-')}", cat_style))
        story.append(Spacer(1, 4))
        story.append(Table([['']], colWidths=[7.0*inch], style=[('LINEBELOW', (0,0), (-1,-1), 1, accent_color)]))
        story.append(Spacer(1, 0.3*inch))

        story.append(Paragraph('Practice Information', section_header))
        t_client = Table([[mk_field('Name', sop.get('client_name')), mk_field('NPI', sop.get('client_npi'))]], colWidths=[3.5*inch]*2)
        t_client.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'), ('PADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e2e8f0')), ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ]))
        story.append(t_client)
        story.append(Spacer(1, 0.2*inch))

        providers = sop.get('providers', [])
        if providers:
            story.append(Paragraph('Provider', section_header))
            prov_list_data = [[Paragraph('<b>Name</b>', pdf_styles['th']), Paragraph('<b>NPI</b>', pdf_styles['th'])]]
            for p in providers:
                prov_list_data.append([Paragraph(p.get('name', '-'), pdf_styles['td']), Paragraph(p.get('npi', '-'), pdf_styles['td'])])
            t_prov_list = Table(prov_list_data, colWidths=[4.5*inch, 2.5*inch])
            t_prov_list.setStyle(table_styles)
            story.append(t_prov_list)
            story.append(Spacer(1, 0.2*inch))

        story.append(Paragraph('Billing Information', section_header))
        p_info = sop.get('provider_info') or {}
        prov_data = [
            [mk_field('Provider Name', p_info.get('providerName')), mk_field('Tax ID', p_info.get('providerTaxID')), mk_field('NPI', p_info.get('billingProviderNPI'))],
            [mk_field('Billing Provider', p_info.get('billingProviderName')), mk_field('Practice Name', sop.get('client_name')), mk_field('Software', p_info.get('software'))],
            [mk_field('Address', p_info.get('billingAddress')), mk_field('Clearinghouse', p_info.get('clearinghouse')), mk_field('Status', sop.get('status', {}).get('code', 'Active'))],
        ]
        t_prov = Table(prov_data, colWidths=[2.333*inch]*3)
        t_prov.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'), ('PADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e2e8f0')), ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ]))
        story.append(t_prov)
        story.append(Spacer(1, 0.2*inch))

        workflow = sop.get("workflow_process") or {}
        if workflow:
            story.append(Paragraph("Workflow Process", section_header))
            description = workflow.get("description") or workflow.get("superbill_source") or "-"
            story.append(Paragraph(description, ParagraphStyle("WorkflowBody", parent=bs, textColor=text_color, fontSize=10, leading=14)))

            posting_rules = workflow.get("posting_charges_rules") or []
            if isinstance(posting_rules, str):
                posting_rules = [posting_rules]
            if posting_rules:
                story.append(Spacer(1, 8))
                story.append(Paragraph("<b>Posting Charges Rules:</b>", ParagraphStyle("PostingHeader", parent=bs, textColor=primary_color, spaceAfter=4)))
                for rule in posting_rules:
                    story.append(Paragraph(f"• {rule}", ParagraphStyle("PostingRule", parent=bs, leftIndent=12, textColor=text_color, spaceAfter=3)))

            portals = workflow.get("eligibility_verification_portals") or workflow.get("eligibilityPortals") or []
            if portals:
                story.append(Spacer(1, 8))
                portal_text = "<b>Eligibility Portals:</b><br/>" + "<br/>".join(f"• {p}" for p in portals)
                story.append(Paragraph(portal_text, ParagraphStyle("Portals", parent=bs, textColor=primary_color, backColor=header_bg, borderPadding=6)))
            story.append(Spacer(1, 0.2 * inch))

        if sop.get('billing_guidelines'):
            story.append(Paragraph('Billing Guidelines', section_header))
            for group in sop.get('billing_guidelines', []):
                story.append(Paragraph(group.get("category", "Guidelines"), ParagraphStyle('BGCategory', parent=styles['Heading3'], textColor=primary_color, fontSize=12, spaceBefore=8, spaceAfter=4)))
                for rule in group.get("rules", []):
                    desc = rule.get("description", "")
                    if desc:
                        story.append(Paragraph(f"• {desc}", ParagraphStyle('BGRule', parent=bs, leftIndent=14, textColor=text_color, fontSize=10, spaceAfter=4)))
            story.append(Spacer(1, 0.15 * inch))

        if sop.get('payer_guidelines'):
            story.append(Paragraph('Payer Guidelines', section_header))
            for pg in sop.get('payer_guidelines', []):
                payer = pg.get('title') or pg.get('payer') or 'Unknown Payer'
                desc = pg.get('description', '-')
                story.append(Paragraph(f"<b>{payer}</b>", ParagraphStyle('PayerTitle', parent=bs, textColor=primary_color, fontSize=11, spaceAfter=2)))
                story.append(Paragraph(desc, ParagraphStyle('PayerDesc', parent=bs, textColor=text_color, leftIndent=10, spaceAfter=8)))
            story.append(Spacer(1, 0.15 * inch))

        if sop.get('coding_rules_cpt'):
            SOPService._build_coding_table(
                story=story, title="CPT Coding Guidelines",
                headers=["CPT", "Description", "NDC", "Units", "Charge", "Modifier", "Replace"],
                rows=sop.get('coding_rules_cpt', []),
                field_map=["cptCode", "description", "ndcCode", "units", "chargePerUnit", "modifier", "replacementCPT"],
                styles=pdf_styles, colors_cfg=table_styles,
            )

        if sop.get('coding_rules_icd'):
            SOPService._build_coding_table(
                story=story, title="ICD Coding Guidelines",
                headers=["ICD Code", "Description", "Notes"],
                rows=sop.get('coding_rules_icd', []),
                field_map=["icdCode", "description", "notes"],
                styles=pdf_styles, colors_cfg=table_styles,
            )

        def add_footer(canvas, doc):
            canvas.saveState()
            canvas.setStrokeColor(colors.HexColor('#e2e8f0'))
            canvas.line(0.75*inch, 0.6*inch, letter[0]-0.75*inch, 0.6*inch)
            canvas.setFont('Helvetica-Bold', 9)
            canvas.setFillColor(colors.HexColor('#94a3b8'))
            canvas.drawRightString(letter[0] - 0.75*inch, 0.35*inch, "docucr")
            canvas.setFont('Helvetica', 9)
            canvas.drawString(0.75*inch, 0.35*inch, f"Page {doc.page}")
            canvas.restoreState()

        doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
        return buffer.getvalue()

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

        active_status_id = db.query(Status.id).filter(
            Status.code == "ACTIVE",
            Status.type == "GENERAL"
        ).scalar()

        if not active_status_id:
            return False

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
        from sqlalchemy.orm import attributes
        from app.services.s3_service import s3_service

        # Helper for adding source to manual entries
        def add_manual_source(items, source_name="Manual"):
            if not items: return items if items else []
            if isinstance(items, list):
                if items and isinstance(items[0], dict) and "rules" in items[0]:
                    # billing_guidelines structure
                    for cat in items:
                        for rule in cat.get("rules", []):
                            if "source" not in rule:
                                rule["source"] = source_name
                else:
                    for item in items:
                        if isinstance(item, dict) and "source" not in item:
                            item["source"] = source_name
            return items

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
            "billing_guidelines": add_manual_source(sop.billing_guidelines),
            "payer_guidelines": add_manual_source(sop.payer_guidelines),
            "coding_rules_cpt": add_manual_source(sop.coding_rules_cpt),
            "coding_rules_icd": add_manual_source(sop.coding_rules_icd),
            "documents": [
                {
                    "id": str(doc.id),
                    "name": doc.name,
                    "category": doc.category,
                    "s3_key": doc.s3_key,
                    # Include the new structured fields
                    "billing_guidelines": doc.billing_guidelines,
                    "payer_guidelines": doc.payer_guidelines,
                    "coding_rules_cpt": doc.coding_rules_cpt,
                    "coding_rules_icd": doc.coding_rules_icd,
                    "document_url": s3_service.generate_presigned_url(
                        doc.s3_key,
                        response_content_disposition=f'inline; filename="{doc.name}"'
                    ),
                    "created_at": doc.created_at,
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

        data["organisation_name"] = sop.organisation.name if sop.organisation else None

        if sop.client:
            data["client_npi"] = sop.client.npi
            if sop.client.business_name:
                data["client_name"] = sop.client.business_name
            else:
                names = [sop.client.first_name, sop.client.middle_name, sop.client.last_name]
                data["client_name"] = " ".join([n for n in names if n]).strip()
        else:
            data["client_name"] = None
            data["client_npi"] = None

        if sop.creator:
            names = [sop.creator.first_name, sop.creator.middle_name, sop.creator.last_name]
            data["created_by_name"] = " ".join([n for n in names if n]).strip()
        elif sop.organisation:
            data["created_by_name"] = sop.organisation.name
        else:
            data["created_by_name"] = None

        data["provider_name"] = None
        if sop.provider_info:
            data["provider_name"] = sop.provider_info.get("providerName")

        return data

    @staticmethod
    def get_sop_by_id(sop_id: str, db: Session, current_user: User = None):
        org_id = SOPService._get_org_id(current_user)

        query = db.query(SOP).filter(SOP.id == sop_id)
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

        if SOPService.check_sop_exists(client_id, provider_ids, db):
            raise HTTPException(
                400,
                "One or more selected providers already have an active SOP for this client."
            )

        db_sop = SOP(**sop_data)
        db.add(db_sop)
        db.commit()
        db.refresh(db_sop)

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
    def process_extra_document(document_id, sop_id, file_content, content_type, category):
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            suffix = ".tmp"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(file_content)
                path = tmp.name

            text = asyncio.run(AISOPService.extract_text(path, content_type))
            structured = asyncio.run(AISOPService.ai_extract_sop_structured(text))

            doc = db.query(SOPDocument).filter(SOPDocument.id == document_id).first()
            sop = db.query(SOP).filter(SOP.id == sop_id).first()

            if not doc or not sop:
                return


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
    def apply_extraction_to_sop(sop, doc, category, extracted):
        # 1. Update document-specific fields
        if doc:
            source_name = "source_file" if doc.category == "Source file" else (doc.name or category or "Document")
            
            def inject_source(items):
                if not items: return items
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            item["source"] = source_name
                            if "rules" in item and isinstance(item["rules"], list): # billing guidelines category
                                for r in item.get("rules", []):
                                    if isinstance(r, dict):
                                        r["source"] = source_name
                return items

            if "Billing" in category:
                doc.billing_guidelines = inject_source(extracted.get("billing_guidelines"))
            elif "Payer" in category:
                doc.payer_guidelines = inject_source(extracted.get("payer_guidelines"))
            elif "Coding" in category or "CPT" in category or "ICD" in category:
                doc.coding_rules_cpt = inject_source(extracted.get("coding_rules_cpt"))
                doc.coding_rules_icd = inject_source(extracted.get("coding_rules_icd"))

        # 2. Update SOP shared fields (Workflow, category, title)
        if category == "Workflow Process":
            sop.workflow_process = extracted.get("workflow_process")

        elif category == "Posting Charges Rules":
            wf = sop.workflow_process or {}
            wf["posting_charges_rules"] = extracted.get("workflow_process", {}).get("posting_charges_rules")
            sop.workflow_process = wf

        elif category == "Eligibility Verification Portals":
            wf = sop.workflow_process or {}
            wf["eligibility_verification_portals"] = extracted.get("workflow_process", {}).get("eligibility_verification_portals")
            sop.workflow_process = wf

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
        structured = asyncio.run(AISOPService.ai_extract_sop_structured(text))

        return structured

    @staticmethod
    def extract_and_apply_document(doc_id: str, sop_id: str):
        """
        Standalone background-safe method: extracts a single document
        and applies it to the SOP. Called by the /documents/process endpoint.
        Uses its own DB session — safe for threading.
        """
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            doc = db.query(SOPDocument).filter(SOPDocument.id == doc_id).first()
            db_sop = db.query(SOP).filter(SOP.id == sop_id).first()

            if not doc or not db_sop:
                print(f"[extraction] Doc {doc_id} or SOP {sop_id} not found")
                return

            extracted = SOPService.extract_from_document(doc)

            category = doc.category or ""

            # Filter to only what this document's category covers
            if "Payer" in category:
                extracted = {"payer_guidelines": extracted.get("payer_guidelines", [])}
            elif "Billing" in category:
                extracted = {"billing_guidelines": extracted.get("billing_guidelines", [])}
            elif "Coding" in category or "CPT" in category or "ICD" in category:
                extracted = {
                    "coding_rules_cpt": extracted.get("coding_rules_cpt", []),
                    "coding_rules_icd": extracted.get("coding_rules_icd", []),
                }
            elif "Workflow" in category:
                extracted = {"workflow_process": extracted.get("workflow_process", {})}
            elif "Eligibility" in category:
                extracted = {"workflow_process": extracted.get("workflow_process", {})}


            SOPService.apply_extraction_to_sop(
                sop=db_sop,
                doc=doc,
                category=category,
                extracted=extracted,
            )

            doc.processed = True
            db.commit()
            print(f"[extraction] ✅ Doc {doc_id} ({doc.name}) processed")

        except Exception as e:
            print(f"[extraction] ❌ Doc {doc_id} failed: {e}")
            # Do NOT mark as processed — allows retry

        finally:
            db.close()

    @staticmethod
    def _sync_guidelines(db_sop: SOP, sop_data: Dict):
        """
        Synchronizes guidelines (billing, payer, cpt, icd) across the main SOP table 
        and its associated SOPDocument records. 
        Items with source='Manual' are saved to the SOP table.
        Items with other sources are saved to their respective SOPDocument records.
        If a document exists but no items are provided for it in the payload, 
        its respective guideline field is cleared (supporting deletions).
        """
        guideline_keys = ["billing_guidelines", "payer_guidelines", "coding_rules_cpt", "coding_rules_icd"]
        
        for key in guideline_keys:
            if key in sop_data and sop_data[key] is not None:
                merged_items = sop_data[key]
                
                # 1. Split items by source
                manual_items_final = []
                doc_groups = {} # {source_name: [items]}
                
                if key == "billing_guidelines":
                    # Special handling for nested category structure
                    for cat_group in merged_items:
                        if not isinstance(cat_group, dict): continue
                        cat_name = cat_group.get("category", "Uncategorized")
                        rules = cat_group.get("rules", [])
                        
                        # Process Manual rules for this category
                        manual_rules = [r for r in rules if r.get("source") == "Manual" or not r.get("source")]
                        if manual_rules:
                            manual_items_final.append({
                                "category": cat_name,
                                "rules": [{"description": r.get("description")} for r in manual_rules]
                            })
                        
                        # Process Extracted rules for this category
                        for r in rules:
                            src = r.get("source")
                            if src and src != "Manual":
                                if src not in doc_groups: doc_groups[src] = {}
                                if cat_name not in doc_groups[src]: doc_groups[src][cat_name] = []
                                doc_groups[src][cat_name].append(r)
                    
                    # Convert doc_groups from dict-of-dicts to list-of-dicts
                    for src in doc_groups:
                        doc_groups[src] = [
                            {"category": cat, "rules": rules} 
                            for cat, rules in doc_groups[src].items()
                        ]
                
                else:
                    # Flat lists (payer_guidelines, coding_rules_*)
                    for item in merged_items:
                        if not isinstance(item, dict): continue
                        src = item.get("source")
                        if src == "Manual" or not src:
                            # Clean up manual item (remove source and temporary IDs)
                            clean_item = item.copy()
                            clean_item.pop("source", None)
                            if key == "payer_guidelines":
                                if "id" in clean_item and isinstance(clean_item["id"], str) and clean_item["id"].startswith("pg_"):
                                    clean_item.pop("id", None)
                            manual_items_final.append(clean_item)
                        else:
                            if src not in doc_groups: doc_groups[src] = []
                            doc_groups[src].append(item)

                # 2. Update SOP table (Manual entries)
                setattr(db_sop, key, manual_items_final)
                
                # 3. Update SOPDocuments (Extracted entries)
                for doc in db_sop.documents:
                    source_name = "source_file" if doc.category == "Source file" else doc.name
                    if source_name in doc_groups:
                        setattr(doc, key, doc_groups[source_name])
                    else:
                        # Clear field if document exists but no items were sent for it (Deletions)
                        # Only clear if the source name was actually present in the extraction pool elsewhere
                        # (to avoid clearing when some unrelated source is being updated)
                        # Actually, since handleSave sends the WHOLE state, if it's not in doc_groups, it's gone.
                        setattr(doc, key, [] if key.startswith("coding_rules") else None)

    @staticmethod
    def update_sop(sop_id: str, sop_data: Dict, db: Session, current_user: User):
        # Extraction is handled exclusively by POST /{sop_id}/documents/process.
        # This method only updates SOP fields and provider mappings.
        org_id = SOPService._get_org_id(current_user)

        db_sop = db.query(SOP).filter(
            SOP.id == sop_id,
            SOP.organisation_id == org_id
        ).first()
        if not db_sop:
            return None

        # ── Provider mappings ──────────────────────────────────────────────────
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

        # ── Unified Guideline Sync ─────────────────────────────────────────────
        SOPService._sync_guidelines(db_sop, sop_data)

        # ── Remaining Field updates ───────────────────────────────────────────
        guideline_fields = {"billing_guidelines", "payer_guidelines", "coding_rules_cpt", "coding_rules_icd"}
        allowed_fields = {
            "title",
            "category",
            "provider_type",
            "client_id",
            "provider_info",
            "workflow_process",
            "status_id",
        }

        for k, v in sop_data.items():
            if k == "provider_ids" or k in guideline_fields:
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

        db.query(SopProviderMapping).filter(SopProviderMapping.sop_id == sop_id).delete()
        db.delete(db_sop)
        db.commit()
        return True

    @staticmethod
    def upgrade_flat_billing_guidelines(flat: list[dict]) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        for item in flat:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "Guidelines").strip()
            desc = item.get("description", "").strip()
            if not desc:
                continue
            grouped.setdefault(title, []).append({"description": desc})

        return [
            {"category": category, "rules": rules}
            for category, rules in grouped.items()
        ]

    @staticmethod
    def _build_coding_table(story, title, headers, rows, field_map, styles, colors_cfg):
        if not rows:
            return

        story.append(Paragraph(title, styles["section_header"]))

        header_row = [Paragraph(f"<b>{h}</b>", styles["th"]) for h in headers]
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
        import copy
        if not isinstance(sop, dict):
            sop = SOPService._format_sop(sop)
        sop = copy.deepcopy(sop)

        # ── Pre-compute extracted doc groups (mirrors SOPReadOnlyView logic) ────
        all_docs = sop.get("documents", [])
        extracted_docs = [d for d in all_docs if d.get("extracted_data")]

        def _ext_by_doc(key, filter_fn):
            result = []
            for doc in extracted_docs:
                items = [x for x in (doc["extracted_data"].get(key) or []) if filter_fn(x)]
                if items:
                    result.append({
                        "name": doc.get("name", ""),
                        "url":  doc.get("document_url") or doc.get("s3_key") or "",
                        "items": items,
                    })
            return result

        ext_billing = _ext_by_doc("billing_guidelines", lambda g: g.get("category") or g.get("rules"))
        ext_payer   = _ext_by_doc("payer_guidelines",   lambda g: g.get("title") or g.get("description"))
        ext_cpt     = _ext_by_doc("coding_rules_cpt",   lambda r: r.get("cptCode") or r.get("description"))
        ext_icd     = _ext_by_doc("coding_rules_icd",   lambda r: r.get("icdCode") or r.get("description"))

        # ── PDF setup ────────────────────────────────────────────────────────────
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter,
            topMargin=0.5*inch, bottomMargin=0.5*inch,
            leftMargin=0.75*inch, rightMargin=0.75*inch)
        base_styles = getSampleStyleSheet()
        story = []

        primary_color = colors.HexColor('#0c4a6e')
        accent_color  = colors.HexColor('#0ea5e9')
        header_bg     = colors.HexColor('#e0f2fe')
        source_bg     = colors.HexColor('#eff6ff')
        source_border = colors.HexColor('#bfdbfe')
        text_color    = colors.HexColor('#334155')
        label_color   = colors.HexColor('#64748b')
        cat_color     = colors.HexColor('#1e40af')
        bs = base_styles['BodyText']

        section_header = ParagraphStyle('SectionHeader', parent=base_styles['Heading2'],
            fontSize=14, textColor=primary_color, spaceBefore=14, spaceAfter=6)
        sub_header = ParagraphStyle('SubHeader', parent=base_styles['Heading3'],
            fontSize=11, textColor=primary_color, spaceBefore=8, spaceAfter=3)
        cat_style = ParagraphStyle('Category', parent=bs,
            fontSize=11, textColor=accent_color, spaceAfter=6, alignment=1)

        pdf_styles = {
            "section_header": section_header,
            "th": ParagraphStyle('TH', parent=bs, textColor=primary_color,
                alignment=1, fontSize=10, fontName='Helvetica-Bold'),
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
            return Paragraph(
                f"<font color='{label_color.hexval()}'><b>{label}</b></font>"
                f"<br/><font color='{text_color.hexval()}'>{value or '-'}</font>", bs)

        def source_badge(name, url=""):
            """
            Renders a pill mirroring DocSourceBadge.
            Left cell: 'Extracted from: filename'
            Right cell: clickable 'View Document →' if a URL is available.
            """
            link_style = ParagraphStyle(
                'SourceLink', parent=bs,
                fontSize=9, textColor=colors.HexColor('#2563eb'),
                alignment=2,  # right-align
            )
            badge_style = ParagraphStyle(
                'SourceBadge', parent=bs,
                fontSize=9, textColor=colors.HexColor('#1d4ed8'),
            )

            left_cell = Paragraph(
                f'<font color="#1d4ed8"><b>&#9679; Extracted from: {name}</b></font>',
                badge_style,
            )

            if url:
                right_cell = Paragraph(
                    f'<link href="{url}"><font color="#2563eb"><u>View Document &#8594;</u></font></link>',
                    link_style,
                )
            else:
                right_cell = Paragraph("", link_style)

            t = Table(
                [[left_cell, right_cell]],
                colWidths=[5.2*inch, 1.8*inch],
            )
            t.setStyle(TableStyle([
                ('BACKGROUND',   (0,0), (-1,-1), source_bg),
                ('BOX',          (0,0), (-1,-1), 0.75, source_border),
                ('ROUNDEDCORNERS', [4]),
                ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
                ('PADDING',      (0,0), (-1,-1), 5),
                ('TOPPADDING',   (0,0), (-1,-1), 6),
                ('BOTTOMPADDING',(0,0), (-1,-1), 6),
            ]))
            return t

        # ── Title ────────────────────────────────────────────────────────────────
        story.append(Paragraph(sop.get('title', 'SOP'),
            ParagraphStyle('MainTitle', parent=base_styles['Title'],
                fontSize=24, textColor=primary_color, spaceAfter=8, leading=28)))
        story.append(Paragraph(sop.get('category', '-'), cat_style))
        story.append(Spacer(1, 4))
        story.append(Table([['']], colWidths=[7.0*inch],
            style=[('LINEBELOW', (0,0), (-1,-1), 1, accent_color)]))
        story.append(Spacer(1, 0.3*inch))

        # ── Practice Information ─────────────────────────────────────────────────
        story.append(Paragraph('Practice Information', section_header))
        t_client = Table(
            [[mk_field('Name', sop.get('client_name')), mk_field('NPI', sop.get('client_npi'))]],
            colWidths=[3.5*inch]*2)
        t_client.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'), ('PADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e2e8f0')),
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ]))
        story.append(t_client)
        story.append(Spacer(1, 0.2*inch))

        # ── Associated Providers ─────────────────────────────────────────────────
        providers = sop.get('providers', [])
        if providers:
            story.append(Paragraph('Associated Providers', section_header))
            prov_data = [[Paragraph('<b>Provider Name</b>', pdf_styles['th']),
                          Paragraph('<b>NPI</b>', pdf_styles['th'])]]
            for p in providers:
                prov_data.append([
                    Paragraph(p.get('name', '-'), pdf_styles['td']),
                    Paragraph(p.get('npi', '-'),  pdf_styles['td'])
                ])
            t_prov = Table(prov_data, colWidths=[4.5*inch, 2.5*inch])
            t_prov.setStyle(table_styles)
            story.append(t_prov)
            story.append(Spacer(1, 0.2*inch))

        # ── Billing Information ──────────────────────────────────────────────────
        story.append(Paragraph('Billing Information', section_header))
        p_info = sop.get('provider_info') or {}
        bi_data = [
            [mk_field('Provider Name', p_info.get('providerName')),
             mk_field('Tax ID',        p_info.get('providerTaxID')),
             mk_field('NPI',           p_info.get('billingProviderNPI'))],
            [mk_field('Billing Provider', p_info.get('billingProviderName')),
             mk_field('Practice Name',    sop.get('client_name')),
             mk_field('Software',         p_info.get('software'))],
            [mk_field('Address',      p_info.get('billingAddress')),
             mk_field('Clearinghouse', p_info.get('clearinghouse')),
             mk_field('Status',        (sop.get('status') or {}).get('code', 'Active'))],
        ]
        t_bi = Table(bi_data, colWidths=[2.333*inch]*3)
        t_bi.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'), ('PADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e2e8f0')),
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ]))
        story.append(t_bi)
        story.append(Spacer(1, 0.2*inch))

        # ── Workflow Process ─────────────────────────────────────────────────────
        workflow = sop.get("workflow_process") or {}
        if workflow:
            story.append(Paragraph("Workflow Process", section_header))
            description = workflow.get("description") or workflow.get("superbill_source") or "-"
            story.append(Paragraph(description,
                ParagraphStyle("WorkflowBody", parent=bs,
                    textColor=text_color, fontSize=10, leading=14)))

            posting_rules = workflow.get("posting_charges_rules") or []
            if isinstance(posting_rules, str):
                posting_rules = [posting_rules]
            if posting_rules:
                story.append(Spacer(1, 8))
                story.append(Paragraph("<b>Posting Charges Rules:</b>",
                    ParagraphStyle("PostingHeader", parent=bs,
                        textColor=primary_color, spaceAfter=4)))
                for rule in posting_rules:
                    story.append(Paragraph(f"• {rule}",
                        ParagraphStyle("PostingRule", parent=bs,
                            leftIndent=12, textColor=text_color, spaceAfter=3)))

            portals = (workflow.get("eligibility_verification_portals")
                       or workflow.get("eligibilityPortals") or [])
            if portals:
                story.append(Spacer(1, 8))
                story.append(Paragraph("<b>Eligibility Verification Portals:</b>",
                    ParagraphStyle("PortalHeader", parent=bs,
                        textColor=primary_color, spaceAfter=4)))
                for portal in portals:
                    story.append(Paragraph(f"• {portal}",
                        ParagraphStyle("Portal", parent=bs,
                            leftIndent=12, textColor=text_color, spaceAfter=3,
                            backColor=header_bg, borderPadding=3)))
            story.append(Spacer(1, 0.2*inch))

        # ── Billing Guidelines ───────────────────────────────────────────────────
        base_billing = sop.get('billing_guidelines') or []
        if base_billing or ext_billing:
            story.append(Paragraph('Billing Guidelines', section_header))

            # Base
            for group in base_billing:
                story.append(Paragraph(group.get("category", "Guidelines"), sub_header))
                for rule in (group.get("rules") or []):
                    desc = rule.get("description", "")
                    if desc:
                        story.append(Paragraph(f"• {desc}",
                            ParagraphStyle('BGRule', parent=bs,
                                leftIndent=14, textColor=text_color,
                                fontSize=10, spaceAfter=4)))

            # Extracted from documents
            for entry in ext_billing:
                story.append(Spacer(1, 6))
                story.append(source_badge(entry["name"], entry.get("url", "")))
                story.append(Spacer(1, 4))
                for group in entry["items"]:
                    story.append(Paragraph(group.get("category", "Guidelines"), sub_header))
                    for rule in (group.get("rules") or []):
                        desc = rule.get("description", "")
                        if desc:
                            story.append(Paragraph(f"• {desc}",
                                ParagraphStyle('ExtBGRule', parent=bs,
                                    leftIndent=14, textColor=text_color,
                                    fontSize=10, spaceAfter=4)))

            story.append(Spacer(1, 0.15*inch))

        # ── Payer Guidelines ─────────────────────────────────────────────────────
        base_payer = sop.get('payer_guidelines') or []
        if base_payer or ext_payer:
            story.append(Paragraph('Payer Guidelines', section_header))

            # Base
            for pg in base_payer:
                payer = pg.get('title') or pg.get('payerName') or pg.get('payer') or 'Unknown Payer'
                desc  = pg.get('description', '-')
                story.append(Paragraph(f"<b>{payer}</b>",
                    ParagraphStyle('PayerTitle', parent=bs,
                        textColor=primary_color, fontSize=11, spaceAfter=2)))
                story.append(Paragraph(desc,
                    ParagraphStyle('PayerDesc', parent=bs,
                        textColor=text_color, leftIndent=10, spaceAfter=8)))

            # Extracted from documents
            for entry in ext_payer:
                story.append(Spacer(1, 6))
                story.append(source_badge(entry["name"], entry.get("url", "")))
                story.append(Spacer(1, 4))
                for pg in entry["items"]:
                    payer = pg.get('title') or pg.get('payerName') or pg.get('payer') or 'Unknown Payer'
                    desc  = pg.get('description', '-')
                    story.append(Paragraph(f"<b>{payer}</b>",
                        ParagraphStyle('ExtPayerTitle', parent=bs,
                            textColor=primary_color, fontSize=11, spaceAfter=2)))
                    story.append(Paragraph(desc,
                        ParagraphStyle('ExtPayerDesc', parent=bs,
                            textColor=text_color, leftIndent=10, spaceAfter=8)))

            story.append(Spacer(1, 0.15*inch))

        # ── CPT Coding Guidelines ────────────────────────────────────────────────
        base_cpt = sop.get('coding_rules_cpt') or []
        if base_cpt or ext_cpt:
            story.append(Paragraph('CPT Coding Guidelines', section_header))

            if base_cpt:
                SOPService._build_coding_table(
                    story=story, title="",
                    headers=["CPT", "Description", "NDC", "Units", "Charge", "Modifier", "Replace"],
                    rows=base_cpt,
                    field_map=["cptCode","description","ndcCode","units",
                               "chargePerUnit","modifier","replacementCPT"],
                    styles=pdf_styles, colors_cfg=table_styles,
                )

            for entry in ext_cpt:
                story.append(Spacer(1, 6))
                story.append(source_badge(entry["name"], entry.get("url", "")))
                story.append(Spacer(1, 4))
                SOPService._build_coding_table(
                    story=story, title="",
                    headers=["CPT", "Description", "NDC", "Units", "Charge", "Modifier", "Replace"],
                    rows=entry["items"],
                    field_map=["cptCode","description","ndcCode","units",
                               "chargePerUnit","modifier","replacementCPT"],
                    styles=pdf_styles, colors_cfg=table_styles,
                )

        # ── ICD Coding Guidelines ────────────────────────────────────────────────
        base_icd = sop.get('coding_rules_icd') or []
        if base_icd or ext_icd:
            story.append(Paragraph('ICD Coding Guidelines', section_header))

            if base_icd:
                SOPService._build_coding_table(
                    story=story, title="",
                    headers=["ICD Code", "Description", "Notes"],
                    rows=base_icd,
                    field_map=["icdCode", "description", "notes"],
                    styles=pdf_styles, colors_cfg=table_styles,
                )

            for entry in ext_icd:
                story.append(Spacer(1, 6))
                story.append(source_badge(entry["name"], entry.get("url", "")))
                story.append(Spacer(1, 4))
                SOPService._build_coding_table(
                    story=story, title="",
                    headers=["ICD Code", "Description", "Notes"],
                    rows=entry["items"],
                    field_map=["icdCode", "description", "notes"],
                    styles=pdf_styles, colors_cfg=table_styles,
                )

        # ── Footer ───────────────────────────────────────────────────────────────
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
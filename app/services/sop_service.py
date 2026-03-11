import asyncio
import copy
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
from io import BytesIO
from app.services.ai_sop_service import AISOPService
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
import datetime
import os
from urllib.parse import quote


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
            "workflow_process": {
                "description": (sop.workflow_process or {}).get("description")
                or (sop.workflow_process or {}).get("workflow_description"),
                "eligibility_verification_portals": (sop.workflow_process or {}).get(
                    "eligibility_verification_portals", []
                ),
                "posting_charges_rules": (sop.workflow_process or {}).get(
                    "posting_charges_rules", []
                ),
            },
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
                        response_content_disposition=f"inline; filename*=UTF-8''{quote(doc.name)}"
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
            data["client_specialty"] = sop.client.specialty
            addr_parts = [
                sop.client.address_line_1,
                sop.client.address_line_2,
                sop.client.city,
                sop.client.state_code,
                sop.client.zip_code
            ]
            data["client_address"] = ", ".join([p for p in addr_parts if p]).strip()
            
            if sop.client.business_name:
                data["client_name"] = sop.client.business_name
            else:
                names = [sop.client.first_name, sop.client.middle_name, sop.client.last_name]
                data["client_name"] = " ".join([n for n in names if n]).strip()
        else:
            data["client_name"] = None
            data["client_npi"] = None
            data["client_specialty"] = None
            data["client_address"] = None

        if sop.creator:
            names = [sop.creator.first_name, sop.creator.middle_name, sop.creator.last_name]
            data["created_by_name"] = " ".join([n for n in names if n]).strip()
        elif sop.organisation:
            data["created_by_name"] = sop.organisation.name
        else:
            data["created_by_name"] = None

        # Providers
        p_info = sop.provider_info or {}
        client_name = data.get("client_name")
        client_npi = data.get("client_npi")

        data["providers"] = [
            {
                "id": str(m.provider.id),
                "name": f"{m.provider.first_name} {m.provider.middle_name or ''} {m.provider.last_name}".strip().replace("  ", " "),
                "first_name": m.provider.first_name,
                "last_name": m.provider.last_name,
                "npi": m.provider.npi,
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
            for m in sop.provider_mappings if m.provider
        ] if hasattr(sop, 'provider_mappings') and sop.provider_mappings else []

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
            joinedload(SOP.documents),
            joinedload(SOP.provider_mappings).joinedload(SopProviderMapping.provider)
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
                
                # Support both snake_case and camelCase during migration
                name = pg.get("payerName") or pg.get("payer_name")
                if name:
                    # Preserve all payer guideline fields
                    normalized_pg = {
                        "payerName": name,
                        "description": pg.get("description", ""),
                        "payerId": pg.get("payerId", pg.get("payer_id", "")),
                        "eraStatus": pg.get("eraStatus", pg.get("era_status", "")),
                        "ediStatus": pg.get("ediStatus", pg.get("edi_status", "")),
                        "tfl": pg.get("tfl", ""),
                        "networkStatus": pg.get("networkStatus", pg.get("network_status", "")),
                        "mailingAddress": pg.get("mailingAddress", pg.get("mailing_address", ""))
                    }
                    normalized.append(normalized_pg)
            sop.payer_guidelines = normalized

        return SOPService._format_sop(sop)

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

                        # Manual + source file stay on SOP
                        if src in ("Manual", "source_file") or not src:

                            clean_item = item.copy()
                            clean_item.pop("source", None)

                            if key == "payer_guidelines":
                                if "id" in clean_item and isinstance(clean_item["id"], str) and clean_item["id"].startswith("pg_"):
                                    clean_item.pop("id", None)

                            manual_items_final.append(clean_item)

                        else:
                            if src not in doc_groups:
                                doc_groups[src] = []
                            doc_groups[src].append(item)
                        # src = item.get("source")
                        # if src == "Manual" or not src:
                        #     # Clean up manual item (remove source and temporary IDs)
                        #     clean_item = item.copy()
                        #     clean_item.pop("source", None)
                        #     if key == "payer_guidelines":
                        #         # Remove temporary frontend IDs but keep all payer guideline fields
                        #         if "id" in clean_item and isinstance(clean_item["id"], str) and clean_item["id"].startswith("pg_"):
                        #             clean_item.pop("id", None)
                        #         # Ensure all payer guideline fields are preserved
                        #         # payerName, description, payerId, eraStatus, ediStatus, tfl, networkStatus, mailingAddress
                        #     manual_items_final.append(clean_item)
                        # else:
                        #     if src not in doc_groups: doc_groups[src] = []
                        #     doc_groups[src].append(item)

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
    def generate_sop_pdf(sop: Any) -> bytes:
        import copy
        if not isinstance(sop, dict):
            sop = SOPService._format_sop(sop)
        sop = copy.deepcopy(sop)

        # ── Pre-compute extracted doc groups (mirrors SOPReadOnlyView logic) ────
        from app.services.s3_service import s3_service
        all_docs = sop.get("documents", [])
        
        def _ext_by_doc(field_name, filter_fn):
            result = []
            image_extensions = ('.png', '.jpg', '.jpeg', '.webp')
            
            for doc in all_docs:
                items = doc.get(field_name) or []
                filtered_items = [x for x in items if filter_fn(x)]
                
                if filtered_items:
                    doc_name = doc.get("name", "")
                    s3_key = doc.get("s3_key")
                    doc_url = s3_service.generate_presigned_url(
                        s3_key,
                        response_content_disposition=f"inline; filename*=UTF-8''{quote(doc_name)}"
                    )
                    
                    is_image = doc_name.lower().endswith(image_extensions)
                    image_data = None
                    
                    if is_image and s3_key:
                        try:
                            # Synchronous S3 fetch for PDF generation context
                            import boto3
                            import base64
                            from botocore.config import Config
                            
                            s3_client = boto3.client(
                                's3',
                                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                                region_name=os.getenv('AWS_REGION', 'us-east-1'),
                                config=Config(signature_version='s3v4')
                            )
                            response = s3_client.get_object(Bucket=os.getenv('AWS_S3_BUCKET'), Key=s3_key)
                            binary_data = response['Body'].read()
                            
                            mime_type = "image/png"
                            if doc_name.lower().endswith(('.jpg', '.jpeg')):
                                mime_type = "image/jpeg"
                            elif doc_name.lower().endswith('.webp'):
                                mime_type = "image/webp"
                                
                            base64_str = base64.b64encode(binary_data).decode('utf-8')
                            image_data = f"data:{mime_type};base64,{base64_str}"
                        except Exception as e:
                            print(f"Error fetching image for PDF: {e}")
                            is_image = False # Fallback to link if fetch fails
                    
                    result.append({
                        "name": doc_name,
                        "url":  doc_url,
                        "data_items": filtered_items,
                        "is_image": is_image,
                        "image_data": image_data
                    })
            return result

        ext_billing = _ext_by_doc("billing_guidelines", lambda g: g.get("category") or g.get("rules"))
        ext_payer   = _ext_by_doc("payer_guidelines",   lambda g: g.get("title") or g.get("payerName") or g.get("payer_name") or g.get("description"))
        ext_cpt     = _ext_by_doc("coding_rules_cpt",   lambda r: r.get("cptCode") or r.get("description"))
        ext_icd     = _ext_by_doc("coding_rules_icd",   lambda r: r.get("icdCode") or r.get("description"))

        # ── HTML/PDF setup ───────────────────────────────────────────────────────
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template("sop_pdf.html")

        html_content = template.render(
            sop=sop,
            ext_billing=ext_billing,
            ext_payer=ext_payer,
            ext_cpt=ext_cpt,
            ext_icd=ext_icd,
            current_date=datetime.datetime.now().strftime("%B %d, %Y")
        )

        buffer = BytesIO()
        HTML(string=html_content).write_pdf(buffer)
        return buffer.getvalue()
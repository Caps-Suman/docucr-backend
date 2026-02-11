from importlib.resources import path
import uuid
from sqlalchemy.orm import Session, defer, joinedload
from sqlalchemy import desc, func, or_
from typing import Optional, List, Dict, Tuple, Any
from app.models.sop import SOP
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
class SOPService:

    @staticmethod
    def _base_visible_sops_query(db: Session):
        active = db.query(Status).filter(
            Status.code == "ACTIVE",
            Status.type == "GENERAL"
        ).first()

        inactive = db.query(Status).filter(
            Status.code == "INACTIVE",
            Status.type == "GENERAL"
        ).first()

        allowed_ids = [s.id for s in (active, inactive) if s]

        if not allowed_ids:
            return db.query(SOP).filter(False)  # explicit empty

        return db.query(SOP).filter(SOP.status_id.in_(allowed_ids))

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

        # Apply visibility filtering
        role_names = [r.name for r in current_user.roles] if not isinstance(current_user, Organisation) else []

        # 1. SUPER_ADMIN
        if current_user.is_superuser or "SUPER_ADMIN" in role_names:
            # Full access, no client join needed for filtering unless searching
            pass
        
        # 2. ORG_ADMIN / Organisation entity
        elif isinstance(current_user, Organisation) or "ORGANISATION_ROLE" in role_names:
            org_id = str(current_user.id) if isinstance(current_user, Organisation) else str(getattr(current_user, 'organisation_id', ''))
            if org_id:
                query = query.filter(SOP.organisation_id == org_id)
            else:
                return [], 0
        
        # 3. Other Roles (Client Admin, etc.)
        else:
            # Fetch assigned client_ids for logged-in user
            assigned_client_ids = db.query(UserClient.client_id).filter(
                UserClient.user_id == str(current_user.id)
            )

            query = query.filter(
                or_(
                    SOP.created_by == str(current_user.id),
                    SOP.client_id.in_(assigned_client_ids)
                )
            )

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
            joinedload(SOP.lifecycle_status)
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
                func.count(SOP.id).label("total"),
                func.count(SOP.id)
                    .filter(Status.code == "ACTIVE")
                    .label("active"),
                func.count(SOP.id)
                    .filter(Status.code == "INACTIVE")
                    .label("inactive"),
            )
            .join(Status, Status.id == SOP.status_id)
            .filter(Status.type == "GENERAL")
        )

        # Apply visibility filtering
        role_names = [r.name for r in current_user.roles] if not isinstance(current_user, Organisation) else []

        if current_user.is_superuser or "SUPER_ADMIN" in role_names:
            pass
        elif isinstance(current_user, Organisation) or "ORGANISATION_ROLE" in role_names:
            org_id = str(current_user.id) if isinstance(current_user, Organisation) else str(getattr(current_user, 'organisation_id', ''))
            if org_id:
                q = q.filter(SOP.organisation_id == org_id)
            else:
                return {"total": 0, "active": 0, "inactive": 0}
        else:
            # Fetch assigned client_ids for logged-in user
            assigned_client_ids = db.query(UserClient.client_id).filter(
                UserClient.user_id == str(current_user.id)
            )

            q = q.filter(
                or_(
                    SOP.created_by == str(current_user.id),
                    SOP.client_id.in_(assigned_client_ids)
                )
            )

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
            "status": {
                "id": sop.lifecycle_status.id,
                "code": sop.lifecycle_status.code,
                "description": sop.lifecycle_status.description
            } if (sop.lifecycle_status and attributes.instance_state(sop).has_identity) else None
        }

        # Organisation Name
        data["organisation_name"] = sop.organisation.name if sop.organisation else None

        # Client Name
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

        # Created By Name
        if sop.creator:
            names = [sop.creator.first_name, sop.creator.middle_name, sop.creator.last_name]
            data["created_by_name"] = " ".join([n for n in names if n]).strip()
        else:
            data["created_by_name"] = None

        return data
    @staticmethod
    def get_sop_by_id(sop_id: str, db: Session) -> Optional[Dict]:
        sop = db.query(SOP).filter(SOP.id == sop_id).options(
            joinedload(SOP.creator),
            joinedload(SOP.organisation),
            joinedload(SOP.client),
            joinedload(SOP.lifecycle_status)
        ).first()
        
        if not sop:
            return None

        # 🔥 BACKWARD COMPAT FIX
        if sop.billing_guidelines:
            first = sop.billing_guidelines[0]
            if isinstance(first, dict) and "title" in first and "rules" not in first:
                sop.billing_guidelines = SOPService.upgrade_flat_billing_guidelines(
                    sop.billing_guidelines
                )

        # Fetch linked providers
        # Assuming SopProviderMapping is available and we can join or query separately.
        # Since SOP model might not have direct relationship set up for 'providers' via secondary table,
        # we can manual query.
        
        # NOTE: If SOP model has `providers` relationship, we can use that.
        # Let's check imports. `Provider` model needed.
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
                "practiceName": p_info.get("practiceName", ""),
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
    def create_sop(sop_data: Dict, db: Session, current_user: Any) -> SOP:
        # Extract provider_ids
        provider_ids = sop_data.pop("provider_ids", [])

        # Generate ID if not present (though model handles default, dict conversion might need it?)
        # Model default is usually enough.
        
        # Handling client relationship if needed
        # If client_id is empty string, set to None
        if 'client_id' in sop_data and not sop_data['client_id']:
            sop_data['client_id'] = None

        # --- Ownership Logic ---
        organisation_id_val = None
        created_by_val = None

        if isinstance(current_user, Organisation):
            created_by_val = None
            organisation_id_val = str(current_user.id)
        elif isinstance(current_user, User):
            if not current_user.is_superuser:
                created_by_val = str(current_user.id)
                if current_user.id:
                    organisation_id_val = str(current_user.organisation_id) if current_user.organisation_id else None
            else:
                created_by_val = None
        
        sop_data['created_by'] = created_by_val
        sop_data['organisation_id'] = organisation_id_val

        # Set default status if missing
        if 'status_id' not in sop_data or sop_data['status_id'] is None:
            active_status = db.query(Status).filter(Status.code == "ACTIVE").first()
            if active_status:
                sop_data['status_id'] = active_status.id
        if not sop_data.get("status_id"):
            active = db.query(Status).filter(
                Status.code == "ACTIVE",
                Status.type == "GENERAL"
            ).first()
            sop_data["status_id"] = active.id

        db_sop = SOP(**sop_data)
        db.add(db_sop)
        db.commit()
        db.refresh(db_sop)

        # Create mappings
        if provider_ids:
             for pid in provider_ids:
                 try:
                     # Check if mapping already exists? No, fresh SOP
                     db.add(SopProviderMapping(
                         sop_id=db_sop.id, 
                         provider_id=pid
                     ))
                 except Exception:
                     # Ignore duplicates or errors for robustness
                     pass
             db.commit()

        return db_sop

    @staticmethod
    def update_sop(sop_id: str, sop_data: Dict, db: Session) -> Optional[SOP]:
        db_sop = SOPService.get_sop_by_id(sop_id, db)
        if not db_sop:
            return None
        
        # --- Provider Update Logic ---
        if 'provider_ids' in sop_data:
            # Get list or empty if None
            provider_ids_raw = sop_data.pop('provider_ids')
            new_provider_ids = set(str(pid) for pid in (provider_ids_raw or []))

            # Fetch existing mappings
            existing_mappings = (
                db.query(SopProviderMapping)
                .filter(SopProviderMapping.sop_id == sop_id)
                .all()
            )
            existing_ids = {str(m.provider_id) for m in existing_mappings}

            to_add = new_provider_ids - existing_ids
            to_remove = existing_ids - new_provider_ids

            # Remove
            if to_remove:
                db.query(SopProviderMapping).filter(
                    SopProviderMapping.sop_id == sop_id,
                    SopProviderMapping.provider_id.in_([uuid.UUID(pid) for pid in to_remove])
                ).delete(synchronize_session=False)

            # Add
            if to_add:
                new_objs = [
                    SopProviderMapping(
                        sop_id=uuid.UUID(sop_id),
                        provider_id=uuid.UUID(pid)
                    )
                    for pid in to_add
                ]
                db.add_all(new_objs)

        # Update other fields
        for key, value in sop_data.items():
            if key == 'client_id' and not value:
                 setattr(db_sop, key, None)
            else:
                setattr(db_sop, key, value)
        
        db.commit()
        
        # Re-fetch full object to include updated providers
        return SOPService.get_sop_by_id(sop_id, db)

    @staticmethod
    def delete_sop(sop_id: str, db: Session) -> bool:
        db_sop = SOPService.get_sop_by_id(sop_id, db)
        if not db_sop:
            return False
        
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
        """Generates a professional PDF version of the SOP."""
        # Ensure sop is a dictionary for consistent access
        if not isinstance(sop, dict):
            sop = SOPService._format_sop(sop)

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.75*inch, rightMargin=0.75*inch)
        styles = getSampleStyleSheet()
        story = []

        # --- Custom Styles & Colors ---
        primary_color = colors.HexColor('#0c4a6e') # Sky 900
        accent_color = colors.HexColor('#0ea5e9')  # Sky 500
        header_bg = colors.HexColor('#e0f2fe')     # Sky 100
        text_color = colors.HexColor('#334155')    # Slate 700
        label_color = colors.HexColor('#64748b')   # Slate 500
        bs = styles['BodyText']

        # Custom Paragraph Styles
        cat_style = ParagraphStyle('Category', parent=bs, fontSize=11, textColor=accent_color, spaceAfter=6, alignment=1)
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

        # Helper to format field with label
        def mk_field(label, value):
            return Paragraph(f"<font color='{label_color.hexval()}'><b>{label}</b></font><br/><font color='{text_color.hexval()}'>{value or '-'}</font>", bs)

        # --- Title Section ---
        title_style = ParagraphStyle('MainTitle', parent=styles['Title'], fontSize=24, textColor=primary_color, spaceAfter=8, leading=28)
        story.append(Paragraph(sop.get('title', 'SOP'), title_style))
        story.append(Paragraph(f"{sop.get('category', '-')}", cat_style))
        
        # Divider Line
        story.append(Spacer(1, 4))
        story.append(Table([['']], colWidths=[7.0*inch], style=[('LINEBELOW', (0,0), (-1,-1), 1, accent_color)]))
        story.append(Spacer(1, 0.3*inch))
        
        # --- Client Information ---
        story.append(Paragraph('Practice Information', section_header))
        client_data = [
            [
                mk_field('Name', sop.get('client_name')),
                mk_field('NPI', sop.get('client_npi'))
            ]
        ]
        t_client = Table(client_data, colWidths=[3.5*inch]*2)
        t_client.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e2e8f0')),
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ]))
        story.append(t_client)
        story.append(Spacer(1, 0.2*inch))

        # --- Associated Providers ---
        providers = sop.get('providers', [])
        if providers:
            story.append(Paragraph('Provider', section_header))
            prov_list_data = [[
                Paragraph('<b>Name</b>', pdf_styles['th']),
                Paragraph('<b>NPI</b>', pdf_styles['th'])
            ]]
            for p in providers:
                prov_list_data.append([
                    Paragraph(p.get('name', '-'), pdf_styles['td']),
                    Paragraph(p.get('npi', '-'), pdf_styles['td'])
                ])
            
            t_prov_list = Table(prov_list_data, colWidths=[4.5*inch, 2.5*inch])
            t_prov_list.setStyle(table_styles)
            story.append(t_prov_list)
            story.append(Spacer(1, 0.2*inch))

        # --- Billing Information ---
        story.append(Paragraph('Billing Information', section_header))
        p_info = sop.get('provider_info') or {}
        
        prov_data = [
            [
                mk_field('Provider Name', p_info.get('providerName')),
                mk_field('Tax ID', p_info.get('providerTaxID')),
                mk_field('NPI', p_info.get('billingProviderNPI'))
            ],
            [
                mk_field('Billing Provider', p_info.get('billingProviderName')),
                mk_field('Practice Name', p_info.get('practiceName')),
                mk_field('Software', p_info.get('software'))
            ],
            [
                mk_field('Address', p_info.get('billingAddress')),
                mk_field('Clearinghouse', p_info.get('clearinghouse')),
                mk_field('Status', sop.get('status', {}).get('code', 'Active'))
            ]
        ]
        
        t_prov = Table(prov_data, colWidths=[2.333*inch]*3)
        t_prov.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e2e8f0')),
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ]))
        story.append(t_prov)
        story.append(Spacer(1, 0.2*inch))
        
        # --- Workflow Process ---
        if sop.get('workflow_process'):
            story.append(Paragraph('Workflow Process', section_header))

            desc = sop.get('workflow_process', {}).get('description', '-')
            story.append(
                Paragraph(
                    desc,
                    ParagraphStyle(
                        'WorkflowBody',
                        parent=bs,
                        textColor=text_color,
                        fontSize=10,
                        leading=14
                    )
                )
            )

            portals = sop.get('workflow_process', {}).get('eligibilityPortals', [])
            if portals:
                story.append(Spacer(1, 8))
                p_text = "<b>Eligibility Portals:</b><br/>" + "<br/>".join(
                    f"• {p}" for p in portals
                )
                story.append(
                    Paragraph(
                        p_text,
                        ParagraphStyle(
                            'Portals',
                            parent=bs,
                            textColor=primary_color,
                            backColor=header_bg,
                            borderPadding=6,
                        )
                    )
                )

            story.append(Spacer(1, 0.2 * inch))


        # --- Billing Guidelines (GROUPED) ---
        if sop.get('billing_guidelines'):
            story.append(Paragraph('Billing Guidelines', section_header))

            for group in sop.get('billing_guidelines', []):
                category = group.get("category", "Guidelines")

                # ✅ Category header (ONCE)
                story.append(
                    Paragraph(
                        category,
                        ParagraphStyle(
                            'BGCategory',
                            parent=styles['Heading3'],
                            textColor=primary_color,
                            fontSize=12,
                            spaceBefore=8,
                            spaceAfter=4
                        )
                    )
                )

                # ✅ Rules under category
                for rule in group.get("rules", []):
                    desc = rule.get("description", "")
                    if not desc:
                        continue

                    story.append(
                        Paragraph(
                            f"• {desc}",
                            ParagraphStyle(
                                'BGRule',
                                parent=bs,
                                leftIndent=14,
                                textColor=text_color,
                                fontSize=10,
                                spaceAfter=4
                            )
                        )
                    )

            story.append(Spacer(1, 0.15 * inch))

        # --- Payer Guidelines ---
        if sop.get('payer_guidelines'):
            story.append(Paragraph('Payer Guidelines', section_header))

            for pg in sop.get('payer_guidelines', []):
                payer = pg.get('payer_name') or pg.get('payer') or 'Unknown Payer'
                desc = pg.get('description', '-')

                story.append(
                    Paragraph(
                        f"<b>{payer}</b>",
                        ParagraphStyle(
                            'PayerTitle',
                            parent=bs,
                            textColor=primary_color,
                            fontSize=11,
                            spaceAfter=2
                        )
                    )
                )

                story.append(
                    Paragraph(
                        desc,
                        ParagraphStyle(
                            'PayerDesc',
                            parent=bs,
                            textColor=text_color,
                            leftIndent=10,
                            spaceAfter=8
                        )
                    )
                )

            story.append(Spacer(1, 0.15 * inch))
   
        # --- Coding Rules ---
        # if sop.coding_rules:
        #     story.append(Paragraph('Coding Rules', section_header))
            
        #     headers = ['CPT', 'Description', 'NDC', 'Units', 'Charge', 'Mod', 'Replace']
        #     # Header Row
        #     table_data = [[Paragraph(f"<b>{h}</b>", ParagraphStyle('TH', parent=bs, textColor=primary_color, alignment=1)) for h in headers]]
            
        #     # Data Rows
        #     def mk_cell(txt, align=0):
        #         return Paragraph(str(txt), ParagraphStyle('TD', parent=bs, textColor=text_color, alignment=align, fontSize=9))

        #     for r in sop.coding_rules:
        #         row = [
        #             mk_cell(r.get('cptCode', ''), 1),
        #             mk_cell(r.get('description', '')),
        #             mk_cell(r.get('ndcCode', ''), 1),
        #             mk_cell(r.get('units', ''), 1),
        #             mk_cell(r.get('chargePerUnit', ''), 1),
        #             mk_cell(r.get('modifier', ''), 1),
        #             mk_cell(r.get('replacementCPT', ''), 1),
        #         ]
        #         table_data.append(row)
            
        #     # Adjusted Column Widths to total exactly 7.0 inch
        #     # [0.85, 2.35, 1.0, 0.55, 0.85, 0.55, 0.85] = 7.0
        #     col_widths = [0.85*inch, 2.35*inch, 1.0*inch, 0.55*inch, 0.85*inch, 0.55*inch, 0.85*inch]
            
        #     rules_table = Table(table_data, colWidths=col_widths, repeatRows=1)
            
        #     # Zebra Striping Logic
        #     ts = TableStyle([
        #         ('BACKGROUND', (0,0), (-1,0), header_bg), # Header BG
        #         ('LINEBELOW', (0,0), (-1,0), 1, accent_color), # Accent line under header
        #         ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        #         ('PADDING', (0,0), (-1,-1), 6),
        #         ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e2e8f0')), # Subtle Grid
        #     ])
            
        #     # Apply Zebra striping manually ensuring it matches data rows
        #     for i in range(1, len(table_data)):
        #         bg = row_odd if i % 2 == 1 else row_even
        #         ts.add('BACKGROUND', (0, i), (-1, i), bg)
                
        #     rules_table.setStyle(ts)
        #     story.append(rules_table)
        if sop.get('coding_rules_cpt'):
            SOPService._build_coding_table(
                story=story,
                title="CPT Coding Guidelines",
                headers=["CPT", "Description", "NDC", "Units", "Charge", "Modifier", "Replace"],
                rows=sop.get('coding_rules_cpt', []),
                field_map=[
                    "cptCode",
                    "description",
                    "ndcCode",
                    "units",
                    "chargePerUnit",
                    "modifier",
                    "replacementCPT",
                ],
                styles=pdf_styles,
                colors_cfg=table_styles,
            )
        if sop.get('coding_rules_icd'):
                SOPService._build_coding_table(
                    story=story,
                    title="ICD Coding Guidelines",
                    headers=["ICD Code", "Description", "Notes"],
                    rows=sop.get('coding_rules_icd', []),
                    field_map=[
                        "icdCode",
                        "description",
                        "notes",
                    ],
                    styles=pdf_styles,
                    colors_cfg=table_styles,
                )

        def add_footer(canvas, doc):
            canvas.saveState()
            # Draw line above footer - Adjusted for 0.75 margin
            canvas.setStrokeColor(colors.HexColor('#e2e8f0'))
            canvas.line(0.75*inch, 0.6*inch, letter[0]-0.75*inch, 0.6*inch)
            
            canvas.setFont('Helvetica-Bold', 9)
            canvas.setFillColor(colors.HexColor('#94a3b8')) # Slate-400
            # Text moved down to 0.35 inch
            canvas.drawRightString(letter[0] - 0.75*inch, 0.35*inch, "docucr")
            
            # Page Number
            canvas.setFont('Helvetica', 9)
            canvas.drawString(0.75*inch, 0.35*inch, f"Page {doc.page}")
            canvas.restoreState()

        doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
        return buffer.getvalue()

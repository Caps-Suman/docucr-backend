from importlib.resources import path
import uuid
from sqlalchemy.orm import Session, defer
from sqlalchemy import desc, func
from typing import Optional, List, Dict, Tuple
from app.models.sop import SOP
from app.models.client import Client
from app.models.status import Status
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
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        status_code: Optional[str] = None
    ) -> Tuple[List[SOP], int]:

        query = SOPService._base_visible_sops_query(db).options(
            defer(SOP.workflow_process),
            defer(SOP.billing_guidelines),
            defer(SOP.coding_rules)
        )

        if status_code:
            status = db.query(Status).filter(
                Status.code == status_code,
                Status.type == "GENERAL"
            ).first()
            if status:
                query = query.filter(SOP.status_id == status.id)

        if search:
            p = f"%{search}%"
            query = query.filter(
                SOP.title.ilike(p) |
                SOP.category.ilike(p) |
                SOP.provider_info["providerName"].astext.ilike(p)
            )

        total = query.count()
        sops = query.order_by(desc(SOP.created_at)).offset(skip).limit(limit).all()
        return sops, total
    @staticmethod
    def get_sop_stats(db: Session) -> Dict[str, int]:
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

        row = q.one()

        return {
            "total_sops": row.total,
            "active_sops": row.active,
            "inactive_sops": row.inactive,
        }
    @staticmethod
    def get_sop_by_id(sop_id: str, db: Session) -> Optional[SOP]:
        return db.query(SOP).filter(SOP.id == sop_id).first()

    @staticmethod
    def create_sop(sop_data: Dict, db: Session) -> SOP:
        # Generate ID if not present (though model handles default, dict conversion might need it?)
        # Model default is usually enough.
        
        # Handling client relationship if needed
        # If client_id is empty string, set to None
        if 'client_id' in sop_data and not sop_data['client_id']:
            sop_data['client_id'] = None

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
        return db_sop

    @staticmethod
    def update_sop(sop_id: str, sop_data: Dict, db: Session) -> Optional[SOP]:
        db_sop = SOPService.get_sop_by_id(sop_id, db)
        if not db_sop:
            return None
        
        for key, value in sop_data.items():
            if key == 'client_id' and not value:
                 setattr(db_sop, key, None)
            else:
                setattr(db_sop, key, value)
        
        db.commit()
        db.refresh(db_sop)
        return db_sop

    @staticmethod
    def delete_sop(sop_id: str, db: Session) -> bool:
        db_sop = SOPService.get_sop_by_id(sop_id, db)
        if not db_sop:
            return False
        
        db.delete(db_sop)
        db.commit()
        return True

    @staticmethod
    def generate_sop_pdf(sop: SOP) -> bytes:
        buffer = BytesIO()
        # Increased margins to 0.75 inch for cleaner, more premium look
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.75*inch, rightMargin=0.75*inch)
        styles = getSampleStyleSheet()
        story = []
        
        # --- Custom Styles & Colors ---
        primary_color = colors.HexColor('#0c4a6e') # Sky 900
        accent_color = colors.HexColor('#0ea5e9')  # Sky 500
        header_bg = colors.HexColor('#e0f2fe')     # Sky 100
        row_even = colors.white
        row_odd = colors.HexColor('#f8fafc')       # Slate 50
        text_color = colors.HexColor('#334155')    # Slate 700
        label_color = colors.HexColor('#64748b')   # Slate 500
        bs = styles['BodyText']

        # Custom Paragraph Styles
        cat_style = ParagraphStyle('Category', parent=bs, fontSize=11, textColor=accent_color, spaceAfter=6, alignment=1)
        section_header = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=14, textColor=primary_color, spaceBefore=12, spaceAfter=6, borderPadding=4)
        
        # --- Title Section ---
        title_style = ParagraphStyle('MainTitle', parent=styles['Title'], fontSize=24, textColor=primary_color, spaceAfter=8, leading=28)
        story.append(Paragraph(sop.title, title_style))
        story.append(Paragraph(f"{sop.category}", cat_style))
        
        # Divider Line - Width 7.0 inch (8.5 - 1.5 margins)
        story.append(Spacer(1, 4))
        story.append(Table([['']], colWidths=[7.0*inch], style=[('LINEBELOW', (0,0), (-1,-1), 1, accent_color)]))
        story.append(Spacer(1, 0.3*inch))
        
        # --- Provider Info ---
        story.append(Paragraph('Provider Information', section_header))
        p_info = sop.provider_info or {}
        
        # Formatted Provider Data with Label styling
        def mk_field(label, value):
            return Paragraph(f"<font color='{label_color.hexval()}'><b>{label}</b></font><br/><font color='{text_color.hexval()}'>{value or '-'}</font>", bs)
            
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
                mk_field('Status', sop.lifecycle_status.code if sop.lifecycle_status else 'Active')
            ]
        ]
        
        # 3 columns, approx 2.33 inch each (Total 7.0)
        t_prov = Table(prov_data, colWidths=[2.333*inch]*3)
        t_prov.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e2e8f0')), # Very light grid
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ]))
        story.append(t_prov)
        story.append(Spacer(1, 0.2*inch))
        
        # --- Workflow Process ---
        if sop.workflow_process:
            story.append(Paragraph('Workflow Process', section_header))
            desc = sop.workflow_process.get('description', '-')
            story.append(Paragraph(desc, ParagraphStyle('WorkflowBody', parent=bs, textColor=text_color, fontSize=10, leading=14)))
            
            portals = sop.workflow_process.get('eligibilityPortals', [])
            if portals:
                story.append(Spacer(1, 8))
                p_text = f"<b>ELIGIBILITY PORTALS:</b>  {', '.join(portals)}"
                story.append(Paragraph(p_text, ParagraphStyle('Portals', parent=bs, textColor=primary_color, backColor=header_bg, borderPadding=6, borderRadius=4)))
            story.append(Spacer(1, 0.2*inch))

        # --- Billing Guidelines ---
        if sop.billing_guidelines:
            story.append(Paragraph('Billing Guidelines', section_header))
            for g in sop.billing_guidelines:
                g_title = g.get('title', 'Guideline')
                g_desc = g.get('description', '')
                story.append(Paragraph(f"<b>{g_title}</b>", ParagraphStyle('GTitle', parent=bs, textColor=primary_color, fontSize=11, spaceAfter=2)))
                story.append(Paragraph(g_desc, ParagraphStyle('GDesc', parent=bs, textColor=text_color, leftIndent=10, spaceAfter=8)))
            story.append(Spacer(1, 0.1*inch))
            
        # --- Coding Rules ---
        if sop.coding_rules:
            story.append(Paragraph('Coding Rules', section_header))
            
            headers = ['CPT', 'Description', 'NDC', 'Units', 'Charge', 'Mod', 'Replace']
            # Header Row
            table_data = [[Paragraph(f"<b>{h}</b>", ParagraphStyle('TH', parent=bs, textColor=primary_color, alignment=1)) for h in headers]]
            
            # Data Rows
            def mk_cell(txt, align=0):
                return Paragraph(str(txt), ParagraphStyle('TD', parent=bs, textColor=text_color, alignment=align, fontSize=9))

            for r in sop.coding_rules:
                row = [
                    mk_cell(r.get('cptCode', ''), 1),
                    mk_cell(r.get('description', '')),
                    mk_cell(r.get('ndcCode', ''), 1),
                    mk_cell(r.get('units', ''), 1),
                    mk_cell(r.get('chargePerUnit', ''), 1),
                    mk_cell(r.get('modifier', ''), 1),
                    mk_cell(r.get('replacementCPT', ''), 1),
                ]
                table_data.append(row)
            
            # Adjusted Column Widths to total exactly 7.0 inch
            # [0.85, 2.35, 1.0, 0.55, 0.85, 0.55, 0.85] = 7.0
            col_widths = [0.85*inch, 2.35*inch, 1.0*inch, 0.55*inch, 0.85*inch, 0.55*inch, 0.85*inch]
            
            rules_table = Table(table_data, colWidths=col_widths, repeatRows=1)
            
            # Zebra Striping Logic
            ts = TableStyle([
                ('BACKGROUND', (0,0), (-1,0), header_bg), # Header BG
                ('LINEBELOW', (0,0), (-1,0), 1, accent_color), # Accent line under header
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('PADDING', (0,0), (-1,-1), 6),
                ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e2e8f0')), # Subtle Grid
            ])
            
            # Apply Zebra striping manually ensuring it matches data rows
            for i in range(1, len(table_data)):
                bg = row_odd if i % 2 == 1 else row_even
                ts.add('BACKGROUND', (0, i), (-1, i), bg)
                
            rules_table.setStyle(ts)
            story.append(rules_table)

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

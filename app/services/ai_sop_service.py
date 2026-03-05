import asyncio
import json
import os
from fastapi import HTTPException
from pdfminer.high_level import extract_text
from docx import Document
from PIL import Image
import base64
from io import BytesIO
import pandas as pd
from app.models.sop import SOP
from app.models.status import Status
from app.services.ai_client import openai_client  # adjust import path
from openpyxl import load_workbook
from pdfminer.high_level import extract_text as pdf_extract

PASS2_SCHEMA = """
{
  "coding_rules_cpt": [
    {
      "cptCode": null,
      "description": null,
      "ndcCode": null,
      "units": null,
      "chargePerUnit": null,
      "modifier": null,
      "replacementCPT": null
    }
  ],
  "coding_rules_icd": [
    {
      "icdCode": null,
      "description": null,
      "notes": null
    }
  ]
}
"""

class AISOPService:

    # ---------- TEXT EXTRACTION ----------

    @staticmethod
    def extract_pdf_text(path: str) -> str:
        return extract_text(path)
    @staticmethod    
    def process_sop_extraction(sop_id: str, file_path: str = None, content_type: str = None, s3_key: str = None):
        from app.core.database import SessionLocal
        from app.services.s3_service import s3_service
        import tempfile

        db = SessionLocal()
        temp_file_to_remove = None

        try:
            # 📁 Handle S3 download if local path is missing (Reanalysis flow)
            if s3_key and not file_path:
                file_extension = s3_key.split('.')[-1] if '.' in s3_key else ''
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}" if file_extension else "") as tmp:
                    # Use asyncio.run since this is a background task (usually sync but we need async S3)
                    file_data = asyncio.run(s3_service.download_file(s3_key))
                    tmp.write(file_data)
                    file_path = tmp.name
                    temp_file_to_remove = file_path

            if not file_path:
                raise Exception("No file source provided for extraction")

            # Extract raw text
            text = asyncio.run(
                AISOPService.extract_text(file_path, content_type)
            )

            structured = asyncio.run(
                AISOPService.ai_extract_sop_structured(text)
            )

            # Get ACTIVE status
            active_status = db.query(Status).filter(
                Status.code == "ACTIVE",
                Status.type == "GENERAL"
            ).first()

            sop = db.query(SOP).filter(SOP.id == sop_id).first()

            if not sop:
                return
            provider_info_raw = structured.get("provider_information") or {}

            normalized_provider_info = {
                "providerName": provider_info_raw.get("billing_provider_name"),
                "billingProviderName": provider_info_raw.get("billing_provider_name"),
                "billingProviderNPI": provider_info_raw.get("billing_provider_npi"),
                "providerTaxID": provider_info_raw.get("provider_tax_id"),
                "billingAddress": provider_info_raw.get("billing_address"),
                "software": provider_info_raw.get("software"),
                "clearinghouse": provider_info_raw.get("clearinghouse"),
            }
            workflow_raw = structured.get("workflow_process") or {}

            normalized_workflow = {
                "description": workflow_raw.get("workflow_description"),
                "eligibility_verification_portals": workflow_raw.get("eligibility_verification_portals", []),
                "posting_charges_rules": workflow_raw.get("posting_charges_rules", [])
            }
            # Update SOP fields
            sop.title = structured.get("basic_information", {}).get("sop_title") or sop.title
            sop.category = structured.get("basic_information", {}).get("category") or sop.category
            sop.provider_info = normalized_provider_info
            sop.workflow_process = normalized_workflow
            sop.billing_guidelines = structured.get("billing_guidelines")
            sop.payer_guidelines = structured.get("payer_guidelines")
            sop.coding_rules_cpt = structured.get("coding_rules_cpt")
            sop.coding_rules_icd = structured.get("coding_rules_icd")

            sop.status_id = active_status.id if active_status else sop.status_id

            db.commit()

        except Exception as e:
            print(f"Error in background extraction: {e}")
            # Mark FAILED
            # FIX: In this DB, FAILED is type 'DOCUMENT'
            failed_status = db.query(Status).filter(
                Status.code == "FAILED",
                Status.type == "DOCUMENT"
            ).first()

            sop = db.query(SOP).filter(SOP.id == sop_id).first()

            if sop and failed_status:
                sop.status_id = failed_status.id
                db.commit()

        finally:
            db.close()
            # Cleanup
            target_path = temp_file_to_remove or file_path
            if target_path and os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except:
                    pass

    @staticmethod
    async def extract_image_text(path: str) -> str:
        """
        Uses OpenAI Vision to extract raw text from an image.
        This replaces pytesseract completely.
        """

        # Read image
        with Image.open(path) as img:
            buffered = BytesIO()
            img.convert("RGB").save(buffered, format="JPEG")
            image_bytes = buffered.getvalue()

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an OCR engine. Extract ALL visible text exactly as-is. No summaries."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all text from this image. Preserve line breaks."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            temperature=0,
            max_tokens=4000
        )

        text = response.choices[0].message.content.strip()

        if not text:
            raise HTTPException(422, "No text extracted from image")

        return text

    @staticmethod
    def extract_docx_text(path: str) -> str:
        doc = Document(path)
        parts = []

        # ---- Paragraphs ----
        for p in doc.paragraphs:
            if p.text.strip():
                parts.append(p.text.strip())

        # ---- Tables ----
        for table_index, table in enumerate(doc.tables, start=1):
            parts.append(f"\n--- TABLE {table_index} START ---")

            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))

            parts.append(f"--- TABLE {table_index} END ---\n")

        return "\n".join(parts)


    @staticmethod
    def extract_excel_text(path: str) -> str:
        try:
            ext = os.path.splitext(path)[1].lower()

            # Handle .xls (old Excel)
            if ext == ".xls":
                df_dict = pd.read_excel(path, sheet_name=None, engine="xlrd")

            # Handle .xlsx
            elif ext in [".xlsx", ".xlsm", ".xltx", ".xltm"]:
                df_dict = pd.read_excel(path, sheet_name=None, engine="openpyxl")

            else:
                raise ValueError(f"Unsupported Excel extension: {ext}")

            full_text = ""

            for sheet_name, df in df_dict.items():
                full_text += f"\n--- Sheet: {sheet_name} ---\n"
                full_text += df.fillna("").astype(str).to_string(index=False)

            return full_text

        except Exception as e:
            raise Exception(f"Excel extraction failed: {str(e)}")
    @staticmethod
    async def extract_text(path: str) -> str:
        """
        Universal extractor for:
        - PDF
        - DOCX
        - XLSX / XLS
        - Images
        """

        ext = os.path.splitext(path)[1].lower()

        # ---------------- PDF ----------------
        if ext == ".pdf":
            return pdf_extract(path)

        # ---------------- DOCX ----------------
        if ext == ".docx":
            doc = Document(path)
            parts = []

            for p in doc.paragraphs:
                if p.text.strip():
                    parts.append(p.text.strip())

            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(
                        cell.text.strip() for cell in row.cells if cell.text
                    )
                    if row_text:
                        parts.append(row_text)

            return "\n".join(parts)

        # ---------------- EXCEL ----------------
        if ext in [".xlsx", ".xlsm", ".xltx", ".xltm"]:
            wb = load_workbook(path, data_only=True)
            parts = []

            for sheet in wb.worksheets:
                parts.append(f"\n--- SHEET: {sheet.title} ---")
                for row in sheet.iter_rows(values_only=True):
                    row_text = " | ".join(
                        str(cell) for cell in row if cell is not None
                    )
                    if row_text.strip():
                        parts.append(row_text)

            return "\n".join(parts)

        # ---------------- OLD XLS ----------------
        if ext == ".xls":
            df_dict = pd.read_excel(path, sheet_name=None, engine="xlrd")
            parts = []

            for sheet_name, df in df_dict.items():
                parts.append(f"\n--- SHEET: {sheet_name} ---")
                parts.append(df.fillna("").astype(str).to_string(index=False))

            return "\n".join(parts)

        # ---------------- IMAGE ----------------
        if ext in [".png", ".jpg", ".jpeg"]:
            with Image.open(path) as img:
                buffered = BytesIO()
                img.convert("RGB").save(buffered, format="JPEG")
                image_bytes = buffered.getvalue()

            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

            response = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Extract all visible text exactly as-is."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract text."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0,
                max_tokens=4000
            )

            return response.choices[0].message.content.strip()

        raise ValueError(f"Unsupported file type: {ext}")
    @staticmethod
    def normalize_ai_sop(data: dict) -> dict:
        category = data.get("category")
        if isinstance(category, dict):
                data["category"] = category.get("title", "")
        elif category is None:
            data["category"] = ""

        guidelines = data.get("billing_guidelines", [])
        payer_guidelines = data.get("payer_guidelines", [])

        normalized = []
        normalized_payers = []

        for pg in payer_guidelines:
            if isinstance(pg, str):
                normalized_payers.append({
                    "title": "Unknown",
                    "description": pg
                })
            elif isinstance(pg, dict):
                normalized_payers.append({
                    "payer_name": pg.get("payer_name") or pg.get("title") or pg.get("payer") or "Unknown",
                    "description": pg.get("description") or ""
                })

        data["payer_guidelines"] = normalized_payers
        for group in guidelines:
            if not isinstance(group, dict):
                continue

            normalized.append({
                "category": group.get("category", "Guidelines"),
                "rules": [
                    {"description": r.get("description", "")}
                    for r in group.get("rules", [])
                    if isinstance(r, dict)
                ]
            })

        data["billing_guidelines"] = normalized
        return data

    @staticmethod
    def safe_parse_json(raw: str) -> dict:
        raw = raw.strip()

        # Remove markdown fences if any
        if raw.startswith("```"):
            raw = raw.replace("```json", "").replace("```", "").strip()

        # Hard stop if it doesn't even look like JSON
        if not raw.startswith("{"):
            raise ValueError("AI did not return JSON")

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # 🔥 Attempt repair
            last_brace = raw.rfind("}")
            if last_brace != -1:
                try:
                    return json.loads(raw[: last_brace + 1])
                except ValueError as e:
                    raise HTTPException(422, str(e))
                except Exception as e:
                    raise HTTPException(500, "Internal server error")


            raise ValueError(f"Invalid JSON from AI:\n{raw[:1000]}")

    # ---------- AI EXTRACTION ----------
    @staticmethod
    async def _call_ai(prompt: str) -> dict:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a strict JSON generator. Output ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            # response_format={"type": "json_object"},
            temperature=0,
            max_tokens=9000
        )

        raw = response.choices[0].message.content.strip()

        # Remove markdown fences if any
        if raw.startswith("```"):
            raw = raw.replace("```json", "").replace("```", "").strip()

        # Extract first JSON object found
        start = raw.find("{")
        end = raw.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise HTTPException(422, f"AI returned non-JSON output:\n{raw[:300]}")

        json_str = raw[start:end + 1]

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise HTTPException(422, f"Invalid JSON from AI: {e}")


    # ---------- PASS 1 ----------

    @staticmethod
    async def extract_narrative_and_rules(text: str) -> dict:
        prompt = """
        You are extracting a medical SOP.

        You are NOT summarizing.
        You are extracting EXACT TEXT.
        Provider information may appear in header, footer, letterhead, signature blocks, or table rows.
        Search entire document before leaving any provider field empty.
        ------------------------------------------------
        BILLING GUIDELINES
        ------------------------------------------------
        Billing guidelines contain ONLY operational or documentation rules.

        Examples:
        - Documentation requirements
        - Authorization requirements
        - Claim submission process
        - Timely filing rules
        - General insurance behavior rules

        DO NOT include any rule that contains:
        - CPT codes
        - HCPCS codes
        - ICD codes
        - Modifiers tied to specific CPT codes

        If a rule contains a CPT or ICD code,
        it MUST be placed in coding_rules_cpt or coding_rules_icd.
        Rules:
        - You MUST infer the category name from surrounding headings or repeated phrases
        - Each group MUST have:
        - category (string)
        - rules (array of objects)
        - Each rule MUST preserve original wording
        - Do NOT mix unrelated rules in the same group
        - Do NOT create empty groups

        --------------------------------
        PAYER GUIDELINES (CRITICAL)
        --------------------------------
        Payer guidelines include:
        - Rules that apply ONLY to a specific insurance payer
        - Mentions of payer names such as Medicare, Medicaid, Aetna, BCBS, UnitedHealthcare, Cigna, etc.
        - Statements like:
        "For Medicare only..."
        "BCBS requires..."
        "Do not bill X to Aetna"
        "Medicaid does not allow..."
        The following items MUST ALWAYS be placed inside payer_guidelines:

        1. ERA setup status
        2. EDI setup information
        3. Claim mailing address
        4. Network / Credentialing status (INN / OON / NA)
        5. Start and End dates for network participation
        6. Timely Filing Limits (TFL)
        7. Payer ID numbers
        8. Claim routing instructions
        9. Remarks specific to a named insurance

        These are NOT billing guidelines.

        Each insurance must be a separate payer_guideline object.

        If a section contains a payer name (Aetna, BCBS, UHC, Medicare, Medicaid, etc.)
        it MUST be categorized as payer_guidelines.
        Rules:
        - EACH payer guideline must be a separate object
        - title MUST be extracted explicitly from the text
        - description MUST preserve original wording
        - If payer-specific rules exist, payer_guidelines MUST NOT be empty
        - DO NOT mix payer rules into billing_guidelines
        
        
        “If the code matches ICD-10 format (letters + numbers like M16.0, Z79.899), place it in coding_rules_icd.
        If numeric CPT/HCPCS format, place it in coding_rules_cpt.
        NEVER mix.”
        
        --------------------------------
        CODING RULES (CRITICAL)
        --------------------------------

        There are TWO distinct coding sections.

        1. CPT CODING RULES
        - Includes ONLY CPT / HCPCS codes
        - CPT codes are numeric (e.g., 99213, J0129, 73502)
        - Includes drug CPTs, infusion CPTs, X-ray CPTs
        - Includes NDC, units, modifiers, charges

        2. ICD CODING RULES
        - Includes ONLY ICD-10 diagnosis codes
        - ICD codes start with a LETTER (e.g., M17.0, Z00.00)
        - Includes diagnosis restrictions, combinations, exclusions
        - MUST NOT include CPTs or NDCs
        # ====================================================
        # CPT CODING RULES
        # ====================================================

        # Extract CPT / HCPCS rules ONLY.

        # CPT codes:
        # Numeric format
        # Examples:
        # 99213
        # 73502
        # J0129

        # Include:
        # - replacement rules
        # - NDC mappings
        # - units
        # - modifiers
        # - charge rules
        # - tables

        # Each row = one object.

        # ====================================================
        # ICD CODING RULES (CRITICAL)
        # ====================================================

        # ICD rules are often written inside sentences.

        # You MUST extract ICD rules even when embedded in text.

        # ICD pattern:
        # Letter + numbers + optional decimal  
        # Examples:
        # M17.0  
        # M54.50  
        # L93.0  

        # Extract from:
        # • replacement rules  
        # • “do not bill together”  
        # • exclusions  
        # • pairing restrictions  
        # • bilateral rules  
        # • “use instead”  
        # • “only when”  

        # Even if multiple ICD codes appear in one sentence:
        # create separate objects.

        # NEVER omit ICD rules.
        STRICT RULES:
        - CPT codes MUST go ONLY into coding_rules_cpt
        - ICD codes MUST go ONLY into coding_rules_icd
        - DO NOT mix CPT and ICD in the same array
        - If a code matches CPT or ICD format, extract it.
        - Do NOT guess

        STRICT SECTION BOUNDARY RULE:

        1. billing_guidelines MUST NEVER contain CPT or ICD codes.
        2. If a rule contains:
        - A numeric CPT code → it MUST go to coding_rules_cpt.
        - A letter-based ICD-10 code (e.g., M54.50, Z79.899) → it MUST go to coding_rules_icd.
        3. billing_guidelines must contain ONLY operational workflow or insurance process rules.
        4. If a rule contains a diagnosis code, it is NOT a billing guideline.
        5. Never duplicate the same rule across sections.
        --------------------------------
        OUTPUT FORMAT (STRICT JSON)
        --------------------------------

        Return ONLY valid JSON in this exact structure.
        Do NOT wrap in markdown.
        Do NOT add explanations.

        {
        "basic_information": {
            "sop_title": "",
            "category": ""
        },

        "provider_information": {
            "billing_provider_name": "",
            "billing_provider_npi": "",
            "provider_tax_id": "",
            "billing_address": "",
            "software": "",
            "clearinghouse": ""
        },

        "workflow_process": {
            "workflow_description": "",
            "eligibility_verification_portals": [],
            "posting_charges_rules": []
        },

        "billing_guidelines": [
            {
            "category": "",
            "rules": [
                { "description": "" }
            ]
            }
        ],

        "payer_guidelines": [
            {
            "title": "",
            "description": ""
            }
        ],

        "coding_rules_cpt": [
            {
            "cptCode": "",
            "description": "",
            "ndcCode": "",
            "units": "",
            "chargePerUnit": "",
            "modifier": "",
            "replacementCPT": ""
            }
        ],

        "coding_rules_icd": [
            {
            "icdCode": "",
            "description": "",
            "notes": ""
            }
        ]
        }
        DOCUMENT:
    """+ text
    #     prompt = f"""
    # You are a medical SOP data extraction engine.

    # You are NOT summarizing.
    # You are NOT interpreting.
    # You are extracting EXACT structured data.

    # Return ONLY valid JSON.
    # Do not include markdown.
    # Do not include explanations.

    # ====================================================
    # OUTPUT JSON STRUCTURE (STRICT)
    # ====================================================

    # {{
    # "basic_information": {{
    #     "sop_title": "",
    #     "category": ""
    # }},

    # "provider_information": {{
    #     "billing_provider_name": "",
    #     "billing_provider_npi": "",
    #     "provider_tax_id": "",
    #     "billing_address": "",
    #     "software": "",
    #     "clearinghouse": ""
    # }},

    # "workflow_process": {{
    #     "description": "",
    #     "eligibility_portals": []
    # }},

    # "billing_guidelines": [
    #     {{
    #     "category": "",
    #     "rules": [
    #         {{ "description": "" }}
    #     ]
    #     }}
    # ],

    # "payer_guidelines": [
    #     {{
    #     "payer_name": "",
    #     "description": ""
    #     }}
    # ],

    # "coding_rules_cpt": [
    #     {{
    #     "cptCode": "",
    #     "description": "",
    #     "ndcCode": "",
    #     "units": "",
    #     "chargePerUnit": "",
    #     "modifier": "",
    #     "replacementCPT": ""
    #     }}
    # ],

    # "coding_rules_icd": [
    #     {{
    #     "icdCode": "",
    #     "description": "",
    #     "ndcCode": "",
    #     "units": "",
    #     "chargePerUnit": "",
    #     "modifier": "",
    #     "replacementCPT": ""
    #     }}
    # ]
    # }}

    # ====================================================
    # GENERAL EXTRACTION RULES
    # ====================================================

    # • Extract only what exists in the document  
    # • Preserve wording  
    # • Do NOT invent data  
    # • If a section is missing → return empty array  
    # • Do NOT merge CPT and ICD  
    # • Do NOT drop rules  
    # ====================================================
    # WORKFLOW PROCESS EXTRACTION (STRICT SPLIT RULES)
    # ====================================================

    # The workflow section often contains TWO different things:

    # 1. Workflow narrative
    # 2. Eligibility portals list

    # These MUST be separated.

    # --------------------------------
    # WORKFLOW DESCRIPTION
    # --------------------------------

    # The workflow description must contain ONLY operational steps such as:
    # - how superbills arrive
    # - how charges are posted
    # - provider grouping rules
    # - internal workflow instructions

    # Include ALL workflow text unless a clear eligibility portal section exists.

    # DO NOT remove text from description unless a line explicitly lists portals.

    # --------------------------------
    # ELIGIBILITY PORTALS
    # --------------------------------

    # Extract portals ONLY if the document clearly contains a portal section.

    # Examples of portal lines:
    # "Eligibility portals:"
    # "Check eligibility in:"
    # "Use Availity / UHC portal"

    # If no portal section exists:
    # → return empty array
    # → keep full workflow text inside description

    # DO NOT guess portals.
    # DO NOT move workflow text into portals.


    # ====================================================
    # BILLING GUIDELINES
    # ====================================================

    # Billing guidelines must be grouped by category.

    # Each group:
    # - category name inferred from heading or context
    # - rules array with original wording

    # Examples of categories:
    # - CPT Replacement Rules
    # - Modifier Rules
    # - Telehealth Billing
    # - Insurance Restrictions
    # - Drug Billing
    # - X-ray Billing

    # Never create empty categories.

    # ====================================================
    # PAYER GUIDELINES
    # ====================================================

    # Extract rules that apply to a specific payer:
    # Medicare, Medicaid, Aetna, BCBS, UHC, etc.

    # Each payer rule must be separate:
    # payer_name + description

    # Never mix payer rules into billing_guidelines.

    # ====================================================
    # CPT CODING RULES
    # ====================================================

    # Extract CPT / HCPCS rules ONLY.

    # CPT codes:
    # Numeric format
    # Examples:
    # 99213
    # 73502
    # J0129

    # Include:
    # - replacement rules
    # - NDC mappings
    # - units
    # - modifiers
    # - charge rules
    # - tables

    # Each row = one object.

    # ====================================================
    # ICD CODING RULES (CRITICAL)
    # ====================================================

    # ICD rules are often written inside sentences.

    # You MUST extract ICD rules even when embedded in text.

    # ICD pattern:
    # Letter + numbers + optional decimal  
    # Examples:
    # M17.0  
    # M54.50  
    # L93.0  

    # Extract from:
    # • replacement rules  
    # • “do not bill together”  
    # • exclusions  
    # • pairing restrictions  
    # • bilateral rules  
    # • “use instead”  
    # • “only when”  

    # Even if multiple ICD codes appear in one sentence:
    # create separate objects.

    # NEVER omit ICD rules.

    # ====================================================
    # STRICT SEPARATION RULE
    # ====================================================

    # If numeric → CPT  
    # If starts with letter → ICD  

    # Never mix.

    # ====================================================
    # DOCUMENT
    # ====================================================

    # {text}
    # """


        return await AISOPService._call_ai(prompt)

    @staticmethod
    async def ai_extract_sop_structured(text: str) -> dict:
        """
        This is the single method your API / frontend should call.
        It orchestrates all extraction passes.
        """

        # PASS 1: Form fields + narrative + rules
        pass1_result = await AISOPService.extract_narrative_and_rules(text)

        # PASS 2: Tables (NDC, X-ray mappings)
        pass2_result = await AISOPService.extract_tables(text)

        # Merge results
        final_result = pass1_result
        final_result["coding_rules_cpt"] = (
            pass1_result.get("coding_rules_cpt", []) +
            pass2_result.get("coding_rules_cpt", [])
        )

        final_result["coding_rules_icd"] = (
            pass1_result.get("coding_rules_icd", []) +
            pass2_result.get("coding_rules_icd", [])
        )

        return final_result
    
    @staticmethod
    async def extract_tables(text: str) -> dict:
        prompt = f"""
Extract ONLY TABULAR DATA.

--------------------------------
CPT TABLE EXTRACTION ONLY
--------------------------------

You MUST extract ONLY CPT-based tables.

These include:
- Infusion CPT + NDC tables
- X-ray CPT modifier tables
- Drug CPT billing tables

RULES:
- Each ROW becomes ONE coding_rules_cpt entry
- CPT code MUST be numeric
- ICD codes MUST NOT appear here
- Use null if a column is missing
- DO NOT create extra keys

--------------------------------
OUTPUT FORMAT (STRICT)
--------------------------------
{PASS2_SCHEMA}

DOCUMENT:
{text}
"""
        return await AISOPService._call_ai(prompt)
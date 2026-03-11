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
from app.services.ai_client import openai_client
from openpyxl import load_workbook
from pdfminer.high_level import extract_text as pdf_extract

# ── Shared JSON schema for table extraction ──────────────────────────────────
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

# ── Shared call helper ────────────────────────────────────────────────────────

async def _call_ai(prompt: str, max_tokens: int = 8000) -> dict:
    """
    Single shared AI caller.
    - Focused prompts need far fewer tokens than the old monolith
    - 3-tier JSON repair fallback
    """
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a medical SOP data extraction assistant. "
                    "Always respond with valid JSON only. No markdown, no explanations."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=max_tokens,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()

    start = raw.find("{")
    end = raw.rfind("}")

    if start == -1:
        raise HTTPException(422, f"AI returned non-JSON:\n{raw[:300]}")

    raw = raw[start:] if (end == -1 or end < start) else raw[start : end + 1]

    # Tier 1
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Tier 2 — json_repair
    try:
        from json_repair import repair_json
        return json.loads(repair_json(raw))
    except Exception:
        pass

    # Tier 3 — truncate to last closing brace
    last = raw.rfind("}")
    if last > 0:
        try:
            return json.loads(raw[:last + 1])
        except Exception:
            pass

    raise HTTPException(422, f"Cannot parse AI JSON:\n{raw[:400]}")


# ── Focused parallel extractors ───────────────────────────────────────────────

async def _extract_meta(text: str) -> dict:
    """Extracts: basic_information + provider_information + workflow_process"""
    prompt = f"""Extract ONLY these sections from the medical SOP below.

Return ONLY this JSON (no extra keys):
{{
  "basic_information": {{"sop_title": "", "category": ""}},
  "provider_information": {{
    "billing_provider_name": "", "billing_provider_npi": "",
    "provider_tax_id": "", "billing_address": "",
    "software": "", "clearinghouse": ""
  }},
  "workflow_process": {{
    "workflow_description": "",
    "eligibility_verification_portals": [],
    "posting_charges_rules": []
  }}
}}

Rules:
- Provider info may appear in headers, footers, letterhead, or signature blocks — search ENTIRE document.
- eligibility_verification_portals: list portal names/URLs.
- posting_charges_rules: list rules about how charges are posted.
- Use "" for missing fields, NOT null.

DOCUMENT:
{text[:12000]}"""
    return await _call_ai(prompt, max_tokens=2000)


async def _extract_billing(text: str) -> dict:
    """Extracts: billing_guidelines only"""
    prompt = f"""Extract ONLY billing guidelines from the medical SOP below.

Billing guidelines = operational/documentation rules ONLY.
Examples: authorization requirements, claim submission rules, timely filing, documentation requirements.

STRICT EXCLUSIONS — do NOT include rules that contain:
- CPT codes (numeric like 99213, J0129)
- ICD-10 codes (letter+number like M17.0)
- Payer-specific rules (those belong in payer_guidelines)

Group rules by their heading/category. Infer category name from surrounding text.

Return ONLY this JSON:
{{
  "billing_guidelines": [
    {{
      "category": "<heading from document>",
      "rules": [{{"description": "<exact original text>"}}]
    }}
  ]
}}

DOCUMENT:
{text[:16000]}"""
    return await _call_ai(prompt, max_tokens=4000)


async def _extract_payers(text: str) -> dict:
    """Extracts: payer_guidelines only"""
    prompt = f"""Extract ONLY payer-specific guidelines from the medical SOP below.

MUST extract:
- ERA setup status (e.g. "Completed", "Form Submitted")
- EDI setup info
- Claim mailing addresses
- Network/credentialing status (INN/OON/NA)
- Timely Filing Limits (TFL)
- Payer ID numbers
- Any rule mentioning a specific payer (Medicare, Medicaid, Aetna, BCBS, UHC, Cigna, etc.)

CRITICAL MERGING RULE:
If the same payer appears in multiple tables/sections, merge ALL their data into ONE object.

STRICT ASSOCIATION:
Only link data (payerId, tfl, etc.) to a payer if EXPLICITLY stated for that payer. No proximity guessing.

Return ONLY this JSON:
{{
  "payer_guidelines": [
    {{
      "payerName": "", "description": "", "payerId": "",
      "eraStatus": "", "ediStatus": "", "tfl": "",
      "networkStatus": "", "mailingAddress": ""
    }}
  ]
}}

DOCUMENT:
{text[:16000]}"""
    return await _call_ai(prompt, max_tokens=6000)


async def _extract_coding(text: str) -> dict:
    """
    Extracts CPT rules from narrative text (inline modifier rules, replacement
    rules, unit caps, admin code rules) AND all ICD rules (replace-with,
    do-not-bill-together, use-only-when).
    Table rows are handled separately by _extract_coding_from_tables.
    """
    prompt = f"""You are extracting CPT and ICD coding rules from a medical SOP.

CPT RULES  ->  coding_rules_cpt
Extract EVERY sentence or rule that mentions a CPT or HCPCS code.

CPT/HCPCS code formats include:
  Numeric: 99213, 73502, 73521, 77080, 96372, 96365, 96366, 96413, 81002
  J-codes: J0129, J0897, J1010, J1200, J2507, J2919, J3489, J7321, j7050, etc.

For EACH rule create ONE object:
  cptCode       -> main CPT/HCPCS code mentioned (e.g. "J0129", "73502")
  description   -> full rule text exactly as written in the document
  modifier      -> any modifier mentioned (e.g. "JZ", "JA", "LT", "RT", "50", "59", "95", "EJ")
  replacementCPT-> if rule says replace X with Y (e.g. "73521")
  units         -> if a specific unit count is mentioned (e.g. "120 max")
  ndcCode       -> leave blank (NDC codes are in tables, not narrative)
  chargePerUnit -> leave blank (charges are in tables, not narrative)

Examples:
  "Please use JZ modifier in all J code CPTs"  -> cptCode:"J-codes", modifier:"JZ"
  "JA modifier should be only use with Medicare for CPT J0129" -> cptCode:"J0129", modifier:"JA"
  "CPT 73502 marked on super bill with LR & RT then use 73521" -> cptCode:"73502", replacementCPT:"73521"
  "CPT J1010 maximum can be billed with 120 units only" -> cptCode:"J1010", units:"120 max"
  "If J7321 is billed more than once, use modifier EJ" -> cptCode:"J7321", modifier:"EJ"
  "For CPT J0897 use admin code 96372 with Aetna" -> TWO objects: J0897 and 96372

ICD RULES  ->  coding_rules_icd
Extract EVERY sentence or rule mentioning an ICD-10 diagnosis code.

ICD-10 format: starts with a LETTER followed by numbers (M17.0, Z00.00, L93.0, M54.50, M1A9XX1)

For EACH ICD code create ONE object:
  icdCode     -> the ICD code exactly as written (e.g. "M17.0", "M54.50")
  description -> full rule text exactly as written
  notes       -> key instruction (e.g. "Replace with M54.59", "Do not bill with M05.89")

CRITICAL: If one sentence mentions multiple ICD codes, create a SEPARATE object for each:
  "M54.50 replace with M54.59"   -> icdCode:"M54.50", notes:"Replace with M54.59"
  "M25.50 replace with M25.59"   -> icdCode:"M25.50", notes:"Replace with M25.59"
  "Do not bill both M45.9 and M05.89 together" -> TWO objects: M45.9 AND M05.89
  "Use M17.0 only when M17.12, M17.9 & M17.11 is given" -> icdCode:"M17.0"

NEVER put CPT codes in coding_rules_icd.
NEVER put ICD codes in coding_rules_cpt.

Return ONLY valid JSON (no markdown, no extra text):
{{
  "coding_rules_cpt": [
    {{"cptCode": "", "description": "", "ndcCode": "", "units": "", "chargePerUnit": "", "modifier": "", "replacementCPT": ""}}
  ],
  "coding_rules_icd": [
    {{"icdCode": "", "description": "", "notes": ""}}
  ]
}}

DOCUMENT:
{text[:20000]}"""
    return await _call_ai(prompt, max_tokens=12000)


async def _extract_coding_from_tables(text: str) -> dict:
    """
    Extracts ALL CPT/HCPCS rows from structured tables.
    Handles BOTH infusion/drug NDC tables AND x-ray modifier/replacement tables.
    """
    table_text = _extract_table_sections(text)
    if not table_text.strip():
        return {"coding_rules_cpt": [], "coding_rules_icd": []}

    prompt = f"""Extract ALL CPT and HCPCS code rows from these medical document tables.

There are TWO types of tables — handle both:

TYPE 1 — Infusion/Drug table (columns: CPT Code | Description | NDC Code | Units | Charge per Unit)
  For each row:
  - cptCode      -> J-code or CPT (e.g. "J0129", "J1010")
  - description  -> drug/procedure name (e.g. "ORENCIA (Injection, abatacept, 10Mg)")
  - ndcCode      -> NDC code exactly as shown (e.g. "00003-2187-13")
  - units        -> unit count or "As per received superbill"
  - chargePerUnit-> charge amount (e.g. "$100.00", "$3750.00")
  - modifier     -> leave blank
  - replacementCPT -> leave blank

TYPE 2 — X-ray/Modifier table (columns: CPT Code | Modifier | Replacement CPT Code)
  For each row:
  - cptCode      -> the CPT code (e.g. "73600", "73510", "72040")
  - description  -> "X-ray code"
  - modifier     -> modifier(s) listed (e.g. "50/LT/RT", "NO Modifier", "Deleted code")
  - replacementCPT -> replacement code if listed (e.g. "73521"), else blank
  - ndcCode, units, chargePerUnit -> leave blank

Rules:
- Extract EVERY row — do NOT skip any
- Preserve exact values (NDC codes, dollar amounts, unit counts)
- Do NOT hallucinate rows not present in the table

Return ONLY valid JSON (no markdown):
{{
  "coding_rules_cpt": [
    {{"cptCode": "", "description": "", "ndcCode": "", "units": "", "chargePerUnit": "", "modifier": "", "replacementCPT": ""}}
  ],
  "coding_rules_icd": []
}}

TABLES:
{table_text}"""
    return await _call_ai(prompt, max_tokens=8000)


def _extract_table_sections(text: str) -> str:
    tables = []
    lines = text.splitlines()
    capture = False
    current: list = []
    for line in lines:
        if "TABLE" in line and "START" in line:
            capture = True
            current = []
        elif "TABLE" in line and "END" in line:
            capture = False
            tables.append("\n".join(current))
        elif capture:
            current.append(line)
    return "\n\n".join(tables)


class AISOPService:

    # ── Text extraction ──────────────────────────────────────────────────────

    @staticmethod
    def extract_pdf_text(path: str) -> str:
        return extract_text(path)

    @staticmethod
    def process_sop_extraction(
        sop_id: str,
        file_path: str = None,
        content_type: str = None,
        s3_key: str = None,
    ):
        from app.core.database import SessionLocal
        from app.services.s3_service import s3_service
        import tempfile

        db = SessionLocal()
        temp_file_to_remove = None

        try:
            if s3_key and not file_path:
                file_extension = s3_key.split(".")[-1] if "." in s3_key else ""
                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=f".{file_extension}" if file_extension else "",
                ) as tmp:
                    file_data = asyncio.run(s3_service.download_file(s3_key))
                    tmp.write(file_data)
                    file_path = tmp.name
                    temp_file_to_remove = file_path

            if not file_path:
                raise Exception("No file source provided for extraction")

            text = asyncio.run(AISOPService.extract_text(file_path))
            structured = asyncio.run(AISOPService.ai_extract_sop_structured(text))

            active_status = db.query(Status).filter(
                Status.code == "ACTIVE", Status.type == "GENERAL"
            ).first()

            sop = db.query(SOP).filter(SOP.id == sop_id).first()
            if not sop:
                return

            structured = AISOPService.normalize_ai_sop(structured)

            sop.title = (
                structured.get("basic_information", {}).get("sop_title") or sop.title
            )
            sop.category = (
                structured.get("basic_information", {}).get("category") or sop.category
            )
            provider_info = structured.get("provider_information") or {}

            if not provider_info.get("billingProviderNPI") and sop.client:
                provider_info["billingProviderNPI"] = sop.client.npi

            sop.provider_info = provider_info
            sop.workflow_process = structured.get("workflow_process")

            from app.models.sop import SOPDocument

            doc = db.query(SOPDocument).filter(
                SOPDocument.sop_id == sop_id,
                SOPDocument.s3_key == s3_key if s3_key else None,
            ).first()

            if not doc:
                doc = db.query(SOPDocument).filter(
                    SOPDocument.sop_id == sop_id,
                    SOPDocument.category == "Source file",
                ).first()

            if doc:
                source_name = (
                    "source_file"
                    if doc.category == "Source file"
                    else (doc.name or "Source File")
                )

                def inject_source(items):
                    if not items:
                        return items
                    for item in items:
                        if isinstance(item, dict):
                            if "rules" in item:
                                for r in item["rules"]:
                                    r["source"] = source_name
                            else:
                                item["source"] = source_name
                    return items

                doc.billing_guidelines = inject_source(
                    structured.get("billing_guidelines")
                )
                doc.payer_guidelines = inject_source(
                    structured.get("payer_guidelines")
                )
                doc.coding_rules_cpt = inject_source(
                    structured.get("coding_rules_cpt")
                )
                doc.coding_rules_icd = inject_source(
                    structured.get("coding_rules_icd")
                )
                doc.processed = True

            sop.status_id = active_status.id if active_status else sop.status_id
            db.commit()

        except Exception as e:
            print(f"Error in background extraction: {e}")
            failed_status = db.query(Status).filter(
                Status.code == "FAILED", Status.type == "DOCUMENT"
            ).first()
            sop = db.query(SOP).filter(SOP.id == sop_id).first()
            if sop and failed_status:
                sop.status_id = failed_status.id
                db.commit()

        finally:
            db.close()
            target_path = temp_file_to_remove or file_path
            if target_path and os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except Exception:
                    pass

    @staticmethod
    async def extract_image_text(path: str) -> str:
        with Image.open(path) as img:
            buffered = BytesIO()
            img.convert("RGB").save(buffered, format="JPEG", quality=92)
            image_bytes = buffered.getvalue()

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an OCR engine. Extract ALL visible text exactly as-is. No summaries.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all text. Preserve line breaks.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            temperature=0,
            max_tokens=4000,
        )

        text = response.choices[0].message.content.strip()
        if not text:
            raise HTTPException(422, "No text extracted from image")
        return text

    @staticmethod
    def extract_docx_text(path: str) -> str:
        doc = Document(path)
        parts = []
        for p in doc.paragraphs:
            if p.text.strip():
                parts.append(p.text.strip())
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
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".xls":
                df_dict = pd.read_excel(path, sheet_name=None, engine="xlrd")
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
        ext = os.path.splitext(path)[1].lower()

        if ext == ".pdf":
            return pdf_extract(path)

        if ext == ".docx":
            doc = Document(path)
            parts = []
            for p in doc.paragraphs:
                if p.text.strip():
                    parts.append(p.text.strip())
            # ✅ Add TABLE markers so _extract_table_sections() can find them
            for table_index, table in enumerate(doc.tables, start=1):
                parts.append(f"\n--- TABLE {table_index} START ---")
                for row in table.rows:
                    row_text = " | ".join(
                        cell.text.strip() for cell in row.cells if cell.text.strip()
                    )
                    if row_text:
                        parts.append(row_text)
                parts.append(f"--- TABLE {table_index} END ---\n")
            return "\n".join(parts)

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

        if ext == ".xls":
            df_dict = pd.read_excel(path, sheet_name=None, engine="xlrd")
            parts = []
            for sheet_name, df in df_dict.items():
                parts.append(f"\n--- SHEET: {sheet_name} ---")
                parts.append(df.fillna("").astype(str).to_string(index=False))
            return "\n".join(parts)

        if ext in [".png", ".jpg", ".jpeg"]:
            return await AISOPService.extract_image_text(path)

        raise ValueError(f"Unsupported file type: {ext}")

    @staticmethod
    def normalize_ai_sop(data: dict) -> dict:
        category = (
            data.get("basic_information", {}).get("category")
            if isinstance(data.get("basic_information"), dict)
            else data.get("category")
        )
        if isinstance(category, dict):
            category = category.get("title", "")

        if "basic_information" not in data:
            data["basic_information"] = {}

        data["basic_information"]["category"] = category or data.get("category", "")
        data["category"] = data["basic_information"]["category"]

        source = "AI Extracted"

        provider_info_raw = data.get("provider_information") or {}
        data["provider_information"] = {
            "providerName": provider_info_raw.get("billing_provider_name")
            or provider_info_raw.get("providerName"),
            "billingProviderName": provider_info_raw.get("billing_provider_name")
            or provider_info_raw.get("billingProviderName"),
            "billingProviderNPI": provider_info_raw.get("billing_provider_npi")
            or provider_info_raw.get("billingProviderNPI"),
            "providerTaxID": provider_info_raw.get("provider_tax_id")
            or provider_info_raw.get("providerTaxID"),
            "billingAddress": provider_info_raw.get("billing_address")
            or provider_info_raw.get("billingAddress"),
            "software": provider_info_raw.get("software"),
            "clearinghouse": provider_info_raw.get("clearinghouse"),
        }

        workflow_raw = data.get("workflow_process") or {}
        data["workflow_process"] = {
            "description": workflow_raw.get("workflow_description")
            or workflow_raw.get("description"),
            "eligibility_verification_portals": workflow_raw.get(
                "eligibility_verification_portals", []
            ),
            "posting_charges_rules": workflow_raw.get("posting_charges_rules", []),
        }

        guidelines = data.get("billing_guidelines", [])
        normalized_guidelines = []
        for group in guidelines:
            if not isinstance(group, dict):
                continue
            normalized_guidelines.append(
                {
                    "category": group.get("category", "Guidelines"),
                    "rules": [
                        {"description": r.get("description", ""), "source": source}
                        for r in group.get("rules", [])
                        if isinstance(r, dict)
                    ],
                }
            )
        data["billing_guidelines"] = normalized_guidelines

        payer_guidelines = data.get("payer_guidelines", [])
        normalized_payers = []
        for pg in payer_guidelines:
            if isinstance(pg, str):
                normalized_payers.append(
                    {
                        "payerName": "Unknown",
                        "description": pg,
                        "payerId": "",
                        "eraStatus": "",
                        "tfl": "",
                        "networkStatus": "",
                        "mailingAddress": "",
                        "source": source,
                    }
                )
            elif isinstance(pg, dict):
                normalized_payers.append(
                    {
                        "payerName": pg.get("payerName")
                        or pg.get("payer_name")
                        or pg.get("title")
                        or pg.get("payer")
                        or "Unknown",
                        "description": pg.get("description") or "",
                        "payerId": pg.get("payerId") or pg.get("payer_id") or "",
                        "eraStatus": pg.get("eraStatus") or pg.get("era_status") or "",
                        "ediStatus": pg.get("ediStatus") or pg.get("edi_status") or "",
                        "tfl": pg.get("tfl") or "",
                        "networkStatus": pg.get("networkStatus")
                        or pg.get("network_status")
                        or "",
                        "mailingAddress": pg.get("mailingAddress")
                        or pg.get("mailing_address")
                        or pg.get("address")
                        or "",
                        "source": pg.get("source") or source,
                    }
                )
        data["payer_guidelines"] = normalized_payers

        for key in ("coding_rules_cpt", "coding_rules_icd"):
            data[key] = [
                {**r, "source": source}
                for r in data.get(key, [])
                if isinstance(r, dict)
            ]

        return data

    @staticmethod
    def safe_parse_json(raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.replace("```json", "").replace("```", "").strip()
        if not raw.startswith("{"):
            raise ValueError("AI did not return JSON")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            last_brace = raw.rfind("}")
            if last_brace != -1:
                try:
                    return json.loads(raw[: last_brace + 1])
                except ValueError as e:
                    raise HTTPException(422, str(e))
                except Exception:
                    raise HTTPException(500, "Internal server error")
            raise ValueError(f"Invalid JSON from AI:\n{raw[:1000]}")

    @staticmethod
    def extract_table_sections(text: str) -> str:
        return _extract_table_sections(text)

    # ── Legacy compat ────────────────────────────────────────────────────────

    @staticmethod
    async def _call_ai(prompt: str) -> dict:
        return await _call_ai(prompt)

    @staticmethod
    async def extract_narrative_and_rules(text: str) -> dict:
        meta, billing, payers, coding = await asyncio.gather(
            _extract_meta(text),
            _extract_billing(text),
            _extract_payers(text),
            _extract_coding(text),
        )
        return {**meta, **billing, **payers, **coding}

    @staticmethod
    async def extract_tables(text: str) -> dict:
        return await _extract_coding_from_tables(text)

    # ── Main entry point ─────────────────────────────────────────────────────

    @staticmethod
    async def ai_extract_sop_structured(text: str) -> dict:
        """
        Fires all 5 extraction calls simultaneously via asyncio.gather.
        Total time ≈ slowest single call (~5-10s) instead of sum of all calls.

        Calls:
          1. _extract_meta        → title, provider, workflow
          2. _extract_billing     → billing guidelines
          3. _extract_payers      → payer guidelines
          4. _extract_coding      → CPT + ICD from narrative text
          5. _extract_coding_from_tables → CPT from table sections
        """
        (
            meta,
            billing,
            payers,
            coding_narrative,
            coding_tables,
        ) = await asyncio.gather(
            _extract_meta(text),
            _extract_billing(text),
            _extract_payers(text),
            _extract_coding(text),
            _extract_coding_from_tables(text),
        )

        # Merge + deduplicate CPT from narrative and table passes
        cpt_combined: list = (
            coding_narrative.get("coding_rules_cpt", [])
            + coding_tables.get("coding_rules_cpt", [])
        )
        seen_cpt: set = set()
        deduped_cpt = []
        for r in cpt_combined:
            key = r.get("cptCode") or r.get("description", "")
            if key and key not in seen_cpt:
                seen_cpt.add(key)
                deduped_cpt.append(r)
            elif not key:
                deduped_cpt.append(r)

        final = {
            **meta,
            **billing,
            **payers,
            "coding_rules_cpt": deduped_cpt,
            "coding_rules_icd": coding_narrative.get("coding_rules_icd", []),
        }

        return AISOPService.normalize_ai_sop(final)
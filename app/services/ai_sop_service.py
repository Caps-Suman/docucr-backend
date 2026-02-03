import json
from fastapi import HTTPException
from pdfminer.high_level import extract_text
from docx import Document
from PIL import Image
import base64
from io import BytesIO

from app.services.ai_client import openai_client  # adjust import path

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
    async def extract_text(path: str, content_type: str) -> str:
        if content_type == "application/pdf":
            return AISOPService.extract_pdf_text(path)

        if content_type in ("image/png", "image/jpeg"):
            return await AISOPService.extract_image_text(path)

        if content_type == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):
            return AISOPService.extract_docx_text(path)

        raise ValueError("Unsupported file type")

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
                    "payer_name": "Unknown",
                    "description": pg
                })
            elif isinstance(pg, dict):
                normalized_payers.append({
                    "payer_name": pg.get("payer_name") or pg.get("payer") or "Unknown",
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

    --------------------------------
    BILLING GUIDELINES (VERY IMPORTANT)
    --------------------------------

    Billing guidelines MUST be GROUPED.

    A "group" represents a FAMILY of rules such as:
    - CPT Code Replacements
    - Modifier Usage
    - ICD Code Restrictions
    - Telehealth Billing
    - Admin Code Usage
    - Insurance-Specific Rules
    - Any other logical heading found in the document

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

    Rules:
    - EACH payer guideline must be a separate object
    - payer_name MUST be extracted explicitly from the text
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

    STRICT RULES:
    - CPT codes MUST go ONLY into coding_rules_cpt
    - ICD codes MUST go ONLY into coding_rules_icd
    - DO NOT mix CPT and ICD in the same array
    - If unsure, OMIT the rule
    - Do NOT guess
    --------------------------------
    OUTPUT FORMAT (STRICT)
    --------------------------------

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
        "superbill_source": "",
        "eligibility_verification_portals": [],
        "posting_charges_rules": ""
    },
   "billing_guidelines": [
    {
        "category": "",
        "rules": [
        { "description": "" }
        ]
    }
    ]
     "payer_guidelines": [
    {
      "payer_name": "",
      "description": ""
    }
  ],
    {
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
    }

    DOCUMENT:
"""+ text

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
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
  "coding_rules": [
    {
      "cptCode": null,
      "description": null,
      "ndcCode": null,
      "units": null,
      "chargePerUnit": null,
      "modifier": null,
      "replacementCPT": null
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
        normalized_guidelines = []

        for g in guidelines:
            if isinstance(g, str):
                normalized_guidelines.append({
                    "title": "Guideline",
                    "description": g
                    })
            elif isinstance(g, dict):
                normalized_guidelines.append({
                    "title": g.get("title") or "Guideline",
                    "description": g.get("description") or ""
                })

        data["billing_guidelines"] = normalized_guidelines
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
#         prompt = """
# You are filling a medical SOP FORM.

# You are NOT summarizing a document.
# You are ANSWERING FORM FIELDS using the document.

# If a field is not explicitly mentioned, return null.
# Do NOT guess.

# --------------------------------
# FORM FIELDS TO FILL
# --------------------------------

# 1. SOP TITLE
# 2. CATEGORY
# 3. BILLING PROVIDER NAME
# 4. BILLING PROVIDER NPI
# 5. PROVIDER TAX ID
# 6. BILLING ADDRESS
# 7. SOFTWARE
# 8. CLEARINGHOUSE
# 9. SUPERBILL SOURCE
# 10. ELIGIBILITY VERIFICATION PORTALS
# 11. POSTING CHARGES RULES

# --------------------------------
# OUTPUT FORMAT (STRICT)
# --------------------------------

# {
#   "basic_information": {
#     "sop_title": "",
#     "category": ""
#   },
#   "provider_information": {
#     "billing_provider_name": "",
#     "billing_provider_npi": "",
#     "provider_tax_id": "",
#     "billing_address": "",
#     "software": "",
#     "clearinghouse": ""
#   },
#   "workflow_process": {
#     "superbill_source": "",
#     "eligibility_verification_portals": [],
#     "posting_charges_rules": ""
#   },
#   "billing_guidelines": [],
#   "coding_rules": []
# }

# DOCUMENT:
# """ + text
        prompt = """
    You are extracting a medical SOP.

    You are NOT summarizing.
    You are extracting EXACT TEXT.

    --------------------------------
    BILLING GUIDELINES (CRITICAL)
    --------------------------------
    Billing guidelines include:
    - Any rule that explains HOW, WHEN, or WHERE charges are billed
    - Modifier usage instructions
    - Deleted CPT instructions
    - Insurance-specific billing rules
    - Posting restrictions
    - "Do not use", "use only", "must bill under", "as per superbill" statements

    Rules:
    - EACH guideline must be a separate object
    - Preserve original wording
    - If at least one billing rule exists, billing_guidelines MUST NOT be empty

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
        "title": "",
        "description": ""
        }
    ],
    "coding_rules": [
    {
      "cptCode": "",
      "description": "",
      "ndcCode": "",
      "units": "",
      "chargePerUnit": "",
      "modifier": "",
      "replacementCPT": ""
    }
    ]
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
        final_result["coding_rules"] = (
            pass1_result.get("coding_rules", []) +
            pass2_result.get("coding_rules", [])
        )

        return final_result
    
    @staticmethod
    async def extract_tables(text: str) -> dict:
        prompt = f"""
Extract ONLY TABULAR DATA.

CRITICAL RULE:
You MUST convert every table row into ONE coding_rules entry.

TABLES:
1. Infusion and NDC Code Table
   - CPT → cptCode
   - NDC → ndcCode
   - Units → units
   - Charge → chargePerUnit

2. X-ray Code Modifier Mapping
   - CPT → cptCode
   - Modifier → modifier

Rules:
- ONE CPT = ONE coding_rules entry
- If CPT appears multiple times, create multiple entries
- Use null if a column is missing
- DO NOT create any extra keys

OUTPUT JSON (STRICT):
{PASS2_SCHEMA}

DOCUMENT:
{text}
"""
        return await AISOPService._call_ai(prompt)
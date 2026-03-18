import json
import io
import base64
from typing import List, Dict, Any
from pdf2image import convert_from_bytes
from PIL import Image
from openai import OpenAIError
import re

from pydantic import fields


class OpenAIDocumentAI:
    MAX_PAGES_PER_REQUEST = 4  # hard limit for stability

    def __init__(self, client, model: str):
        self.client = client
        self.model = model

    # ---------- helpers ----------

    def _extract_json_from_response(self, response) -> Dict[str, Any]:
        """
        Correctly extract JSON from OpenAI Responses API output objects.
        """
        for message in response.output:
            for block in message.content:
                if block.type == "output_text":
                    text = (block.text or "").strip()
                    if not text:
                        continue

                    # Strip markdown fences if present
                    text = re.sub(r"^```json|```$", "", text, flags=re.MULTILINE).strip()

                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as e:
                        raise RuntimeError(
                            f"Invalid JSON from model.\nText:\n{text}"
                        ) from e

        raise RuntimeError(
            f"No JSON output found. Full response: {response}"
        )

    def _encode_image(self, image: Image.Image) -> str:
        if image.mode != "RGB":
            image = image.convert("RGB")

        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _pdf_to_images(self, file_bytes: bytes) -> List[str]:
        pages = convert_from_bytes(file_bytes)
        return [self._encode_image(p) for p in pages]

    def _chunk(self, items: List[str], size: int):
        for i in range(0, len(items), size):
            yield items[i:i + size]

    # ---------- main ----------
    async def classify_pages(self, images: List[str], schemas: List[Dict[str, Any]]):
        available_types = ", ".join([s["type_name"] for s in schemas])
        system_prompt = f"""
    You are a medical document segmentation engine.

    Your job is to classify EACH page independently.

    CRITICAL DEFINITIONS:

    - A PAGE = exactly one input image.
    - A DOCUMENT = one complete medical form that belongs to one patient.
    - Pages must NOT be grouped.
    - Never assume pages belong together unless explicitly instructed.
    - Treat every page as isolated.

    AVAILABLE DOCUMENT TYPES:
    {available_types}

    BOUNDARY DETECTION RULES (STRICT):

    1. If a page contains a header with:
    - "PATIENT"
    - "DOB"
    - "DATE"
    - Clinic name (e.g., Greater Washington Arthritis...)
    
    Then this page is the START of a new document.

    2. If a page does NOT contain patient header fields but contains:
    - ICD-10 diagnosis grid
    - Continuation of diagnosis table
    - No new patient header
    
    Then this page is a CONTINUATION page.

    3. Never merge pages.
    4. Never assume continuation unless header is clearly absent.
    5. If patient name or DOB changes → that is a new document.
    6. Even if document type is the same, header repetition means NEW document.

    PATIENT NAME EXTRACTION RULES:

    - Extract patient name ONLY from the header next to "PATIENT".
    - If not visible on the page, return null.
    - Do NOT guess patient name from other pages.
    - Do NOT reuse previous page patient name.

    OUTPUT FORMAT (STRICT JSON ONLY):

    {
    "pages": [
        {
        "page_number": 1,
        "document_type": "SUPERBILL",
        "is_new_document": true,
        "patient_name": "John Doe",
        "dob": "MM/DD/YYYY"
        }
    ]
    }

    STRICT REQUIREMENTS:

    - One object per page.
    - Never omit a page.
    - Never return arrays inside fields.
    - Never add explanations.
    - JSON only.
    - Deterministic output.
    """

        results = []

        for chunk_index, page_group in enumerate(self._chunk(images, self.MAX_PAGES_PER_REQUEST)):
            user_content = [{"type": "input_text", "text": "Classify each page"}]

            for img in page_group:
                user_content.append({
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{img}"
                })

            response = await self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}]
                    },
                    {
                        "role": "user",
                        "content": user_content
                    }
                ],
                max_output_tokens=800
            )

            chunk_result = self._extract_json_from_response(response)

            start_page = chunk_index * self.MAX_PAGES_PER_REQUEST

            for p in chunk_result.get("pages", []):
                p["page_number"] += start_page
                results.append(p)

        return results
    
    def group_pages(self, page_results: List[Dict[str, Any]]):
        page_results = sorted(page_results, key=lambda x: x["page_number"])

        grouped = []
        current_doc = None

        for page in page_results:
            if page.get("is_new_document") or current_doc is None:
                if current_doc:
                    grouped.append(current_doc)

                current_doc = {
                    "type_name": page["document_type"],
                    "pages": [page["page_number"]]
                }
            else:
                current_doc["pages"].append(page["page_number"])

        if current_doc:
            grouped.append(current_doc)

        return grouped

    async def extract_fields_for_document(self, images, group, schema):

        # 1️⃣ Build dynamic field instructions
        field_instructions = []

        for field in schema.get("fields", []):
            field_name = field["fieldName"]
            field_type = field.get("fieldType", "TEXT")
            description = field.get("description", "")

            field_instructions.append(
                f"""Field Name: {field_name}
    Field Type: {field_type}
    Description: {description if description else "No description provided."}
    """
            )

        # 2️⃣ Build output structure dynamically
        output_structure = ",\n".join(
            [f'"{f["fieldName"]}": null' for f in schema.get("fields", [])]
        )

        # 3️⃣ Now build system prompt
        system_prompt = f"""
    You are a structured document data extraction engine.

    You are extracting data for document type: {group['type_name']}.

    Below are the fields defined in the active template:

    {chr(10).join(field_instructions)}

    ---------------------------------------------------
    STRICT RULES
    ---------------------------------------------------

    1. Extract ONLY the fields listed above.
    2. If a field is missing, return null.
    3. Do NOT invent values.
    4. Do NOT extract unrelated data.
    5. Be conservative — if unsure, return null.
    6. Preserve original formatting unless normalization is obvious (e.g., dates).
    7. Do NOT return arrays unless fieldType explicitly requires it.

    ---------------------------------------------------
    OUTPUT FORMAT (STRICT JSON ONLY)
    ---------------------------------------------------

    {{
    "fields": {{
        {output_structure}
    }}
    }}

    Return JSON only.
    """

        selected_images = [images[p - 1] for p in group["pages"]]

        user_content = [{"type": "input_text", "text": "Extract fields"}]

        for img in selected_images:
            user_content.append({
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{img}"
            })

        response = await self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}]
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            max_output_tokens=1000
        )

        result = self._extract_json_from_response(response)

        return {
            "type_name": group["type_name"],
            "pages": group["pages"],
            "fields": result.get("fields", {})
        }
    
    async def analyze(self, file_bytes, filename, schemas):

        if not filename.lower().endswith(".pdf"):
            raise ValueError("Unsupported file type")

        images = self._pdf_to_images(file_bytes)

        final_documents = []

        # --- DETERMINISTIC SEGMENTATION ---
        # Rule: Every page containing DOB is start of new superbill

        header_pages = []

        for idx, img in enumerate(images):
            page_number = idx + 1

            # Quick lightweight header detection using AI but NOT segmentation
            response = await self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": [{
                            "type": "input_text",
                            "text": """
                            Look at this page.

                            If this page contains a patient header section with:
                            - The word DOB
                            - A date formatted like MM/DD/YYYY or YYYY-MM-DD
                            - A patient name near the top

                            Extract the Date of Birth.

                            If no DOB is visible on this page, return null.

                            OUTPUT FORMAT (JSON ONLY):
                            {
                            "dob": "MM/DD/YYYY or null"
                            }
                            """
                        }]
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{img}"}
                        ]
                    }
                ],
                max_output_tokens=10
            )

            answer = ""
            for m in response.output:
                for block in m.content:
                    if block.type == "output_text":
                        answer = (block.text or "").strip().lower()

            parsed = self._extract_json_from_response(response)
            dob = parsed.get("dob")

            if dob:
                header_pages.append(page_number)

        # If no headers detected, fallback: treat every page as independent
        if not header_pages:
            header_pages = list(range(1, len(images) + 1))

        # Build groups deterministically
        groups = []

        for i, start_page in enumerate(header_pages):
            if i + 1 < len(header_pages):
                end_page = header_pages[i + 1] - 1
            else:
                end_page = len(images)

            groups.append({
                "type_name": "SUPERBILL",
                "pages": list(range(start_page, end_page + 1))
            })

        # --- Extraction per grouped superbill ---
        for group in groups:

            schema = next(
                (s for s in schemas if s["type_name"] == "SUPERBILL"),
                None
            )

            if not schema:
                continue

            extracted = await self.extract_fields_for_document(
                images,
                group,
                schema
            )

            page_range = (
                f"{group['pages'][0]}"
                if len(group["pages"]) == 1
                else f"{group['pages'][0]}-{group['pages'][-1]}"
            )
            if not extracted.get("fields"):
                print("⚠️ EMPTY FIELDS FOR:", page_range)
            final_documents.append({
                "type": "SUPERBILL",
                "page_range": page_range,
                "confidence": 1.0,
                "data": {
                    "fields": extracted.get("fields", {})
                }
            })

        return {
            "findings": final_documents
        }
#     async def analyze(
#         self,
#         file_bytes: bytes,
#         filename: str,
#         schemas: List[Dict[str, Any]]
#     ) -> Dict[str, Any]:

#         images: List[str] = []
#         if filename.lower().endswith(".pdf"):
#             images = self._pdf_to_images(file_bytes)
#         schemas_text = "\n\nAVAILABLE DOCUMENT TYPES AND FIELDS:\n"

#         for schema in schemas:
#             schemas_text += f"\nDocument Type: {schema['type_name']}\n"
#             schemas_text += "Fields:\n"
#             for field in schema.get("fields", []):
#                 schemas_text += f"- {field}\n"
#         system_prompt = ('''
#                 You are a medical document classification and extraction engine.
#         {schemas_text}

#         DEFINITIONS:
#         - A "page" refers to a single input image.
#         - A "document" is one or more consecutive pages that belong together.
#         - Each page MUST belong to exactly ONE document.
#         - Each document MUST have exactly ONE document type.

#         ALLOWED DOCUMENT TYPES:
#         Use ONLY the document types defined in the schemas.
#         Do NOT invent new types.

#         STRICT RULES (NON-NEGOTIABLE):
#         1. For any given page, assign ONLY ONE document type.
#         2. NEVER produce more than one document type for the same page.
#         3. If multiple pages belong to the same document, MERGE them into a single document.
#         4. NEVER duplicate the same document more than once.
#         5. If a document spans multiple pages, output it ONCE.
#         6. If information is missing, use null — DO NOT duplicate documents.
#         7. The output MUST be deterministic and deduplicated.

#         FIELD EXTRACTION RULES:
#         - Extract ONLY fields defined in the schema for that document type.
#         - Output ALL fields for a document in a SINGLE object.
#         - Do NOT repeat the same field multiple times.
#         - Normalize field names exactly as defined in the schema.

#         OUTPUT FORMAT (STRICT):
#         Return a JSON object with this exact structure:

#         {
#         "documents": [
#             {
#             "type_name": "<DOCUMENT_TYPE>",
#             "pages": [<page_numbers>],
#             "fields": {
#                 "<field_name>": "<value or null>"
#             }
#             }
#         ]
#         }

#         IMPORTANT:
#         - NEVER return nested "documents" arrays.
#         - NEVER return duplicate documents.
#         - NEVER return arrays of fields — fields MUST be a single object.
#         - If a page was classified once, DO NOT classify it again.

#         OUTPUT JSON ONLY.
#         NO explanations.
#         NO markdown.
# '''
#         )

#         results: List[Dict[str, Any]] = []

#         try:
#             for chunk_index, page_group in enumerate(self._chunk(images, self.MAX_PAGES_PER_REQUEST)):
#                 user_content = [
#                     {"type": "input_text", "text": "Analyze this document"}
#                 ]

#                 for img in page_group:
#                     user_content.append({
#                         "type": "input_image",
#                         "image_url": f"data:image/jpeg;base64,{img}"
#                     })

#                 response = await self.client.responses.create(
#                     model=self.model,
#                     input=[
#                         {
#                             "role": "system",
#                             "content": [{"type": "input_text", "text": system_prompt}]
#                         },
#                         {
#                             "role": "user",
#                             "content": user_content
#                         }
#                     ],
#                     max_output_tokens=1200
#                 )

#                 chunk_result = self._extract_json_from_response(response)

#                 # 🔥 Adjust page numbers to global page index
#                 start_page = chunk_index * self.MAX_PAGES_PER_REQUEST

#                 documents = chunk_result.get("documents", [])
#                 for doc in documents:
#                     if "pages" in doc:
#                         doc["pages"] = [p + start_page for p in doc["pages"]]

#                 results.append({
#                     "documents": documents
#                 })
#         except OpenAIError as e:
#             raise RuntimeError(f"OpenAI request failed: {e}")

#         # Merge chunk results (simple merge strategy)
#         # -------------------------------
#         # 🔥 GLOBAL MERGE ACROSS CHUNKS
#         # -------------------------------

#         merged_documents = {}

#         for chunk in results:
#             for doc in chunk.get("documents", []):
#                 doc_type = doc.get("type_name")
#                 pages = doc.get("pages", [])
#                 fields = doc.get("fields", {})

#                 if not doc_type:
#                     continue

#                 if doc_type not in merged_documents:
#                     merged_documents[doc_type] = {
#                         "type_name": doc_type,
#                         "pages": set(),
#                         "fields": {}
#                     }

#                 # Merge pages
#                 merged_documents[doc_type]["pages"].update(pages)

#                 # Merge fields
#                 for field_name, value in fields.items():
#                     if value is None or value == "":
#                         continue

#                     existing_value = merged_documents[doc_type]["fields"].get(field_name)

#                     # If field doesn't exist yet
#                     if not existing_value:
#                         merged_documents[doc_type]["fields"][field_name] = value
#                         continue

#                     # If both are strings → treat as comma-separated lists
#                     if isinstance(existing_value, str) and isinstance(value, str):
#                         existing_set = set([v.strip() for v in existing_value.split(",") if v.strip()])
#                         new_set = set([v.strip() for v in value.split(",") if v.strip()])
#                         combined = sorted(existing_set | new_set)
#                         merged_documents[doc_type]["fields"][field_name] = ", ".join(combined)
#                     else:
#                         # If non-string (rare case), override safely
#                         merged_documents[doc_type]["fields"][field_name] = value

#         # Convert sets back to sorted lists
#         final_documents = []

#         for doc in merged_documents.values():
#             final_documents.append({
#                 "type_name": doc["type_name"],
#                 "pages": sorted(list(doc["pages"])),
#                 "fields": doc["fields"]
#             })

#         return {
#             "documents": final_documents
#         }
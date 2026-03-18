from collections import Counter
import os
import io
import json
import base64
import asyncio
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from openai import AsyncOpenAI
from pdf2image import convert_from_bytes
from PIL import Image

from app.models.unverified_document import UnverifiedDocument


class AIService:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _encode_image(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGB")
        image.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    async def _convert_to_images(self, file_content: bytes, filename: str) -> List[str]:
        if filename.lower().endswith(".pdf"):
            loop = asyncio.get_event_loop()
            pages = await loop.run_in_executor(
                None,
                lambda: convert_from_bytes(file_content, dpi=200)
            )
            encoded = await loop.run_in_executor(
                None,
                lambda: [self._encode_image(p) for p in pages]
            )
            return encoded
        image = Image.open(io.BytesIO(file_content))
        return [self._encode_image(image)]

    def _safe_parse_json(self, raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        try:
            from json_repair import repair_json
            return json.loads(repair_json(raw))
        except Exception:
            pass
        last = raw.rfind("}")
        if last != -1:
            try:
                return json.loads(raw[:last + 1])
            except Exception:
                pass
        raise ValueError(f"Cannot parse JSON:\n{raw[:400]}")

    def build_document_instances(self, pages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Group consecutive pages into document instances.

        header_restart=False means "this page is a continuation of the previous one".
        When a page is a continuation, it is ALWAYS merged with the previous instance
        regardless of whether the classifier returned a different type name.
        This correctly handles multi-page forms (e.g. DXA front+back) where the
        back page may be classified as a different type due to visual differences.

        A new instance starts ONLY when:
          - header_restart=True (new patient header / new form start detected), OR
          - header_restart=True (default) and type changed
        """
        documents = []
        current = None

        for page in pages:
            if current is None:
                current = {
                    "type": page["type"],
                    "start": page["page"],
                    "end": page["page"],
                }
                continue

            is_continuation = not page.get("signals", {}).get("header_restart", True)

            if is_continuation:
                # Always merge with previous — ignore type name differences.
                # The page type stays as the FIRST page's type (authoritative).
                current["end"] = page["page"]
            else:
                # New patient header or new form → start a new instance
                documents.append(current)
                current = {
                    "type": page["type"],
                    "start": page["page"],
                    "end": page["page"],
                }

        if current:
            documents.append(current)

        return [
            {"type": d["type"], "page_range": f"{d['start']}-{d['end']}"}
            for d in documents
        ]

    # ------------------------------------------------------------------
    # Phase 1 — Classify all pages in parallel (fully dynamic)
    # ------------------------------------------------------------------

    async def _classify_all_pages(
        self,
        images: List[str],
        document_types: List[Dict[str, str]],  # [{name, description}, ...]
        max_concurrent: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Classify each page against the org's document types.
        All type names and descriptions come from the DB — nothing hardcoded here.
        """

        # Build type listing from DB data only
        type_lines = []
        for dt in document_types:
            name = dt["name"]
            desc = dt.get("description", "").strip()
            if not desc:
                # DB has no description — use a minimal fallback so the
                # prompt is still valid. Admin should fill in descriptions
                # for best results.
                desc = f"A document of type {name.replace('_', ' ').title()}."
            type_lines.append(f"■ {name}\n  {desc}")

        document_type_block = "\n\n".join(type_lines)
        valid_names = {dt["name"] for dt in document_types}
        type_list_str = " | ".join(sorted(valid_names)) + " | UNKNOWN"

        system_prompt = (
            "You are a precise medical document page classifier. "
            "Respond with valid JSON only. No markdown, no explanation."
        )

        user_prompt_template = f"""Classify this medical document page image.

AVAILABLE DOCUMENT TYPES:
{document_type_block}

CLASSIFICATION RULES:
1. First try to match the page to one of the listed types above using the description.
2. If the page clearly matches one of the listed types → use that type name exactly.
3. If the page does NOT match any listed type → INVENT a concise, descriptive type name:
   - Use ALL_CAPS with underscores (e.g. DXA_ORDER, INSURANCE_CARD, LAB_REPORT)
   - Describe WHAT the document is (its form type), not what data it contains
   - Common examples: DXA_DIAGNOSTIC_CODES, INSURANCE_CARD, FINANCIAL_RESPONSIBILITY,
     LAB_RESULTS, REFERRAL_FORM, CONSENT_FORM, PRIOR_AUTH, PATIENT_INTAKE
   - NEVER return "UNKNOWN" — always invent a meaningful descriptive name
   - NEVER return "UNCLASSIFIED" — always invent a meaningful descriptive name

GROUPING — header_restart controls how pages are counted as documents.
Get this right — it determines how many document instances are reported.

header_restart = true  → this page STARTS a new document (new patient / new form)
header_restart = false → this page CONTINUES the previous page (same patient, same form)

RULES for header_restart:
  TRUE when: a new patient name and/or date of birth is visible at the top of this page
  FALSE when: no patient header at top — this is a back page or continuation page

ALWAYS false (continuation) for these page types:
  • A diagnosis/ICD-10 list page (shows "H. DIAGNOSIS" header, alphabetical diagnoses,
    "Signed out By" — this is the BACK of a superbill, same patient, same visit)
  • A page showing diagnosis categories like "Osteoporosis", "Ovary", "Parathyroid",
    "Thyroid", "V Codes", "Pituitary" with ICD codes — this is the BACK of a DXA order
    form. Classify it as the SAME type as the previous page and set header_restart=false.
  • Page 2+ of any multi-page form with no new patient block at the top
  • Any page that has NO patient name/DOB written at the top

ALWAYS true (new instance) for:
  • A page with a patient name handwritten at the top (even if same doc type as previous)
  • First page of any form that has the practice letterhead and patient info fields

Return ONLY this JSON:
{{
  "type": "<one of: {type_list_str}>",
  "confidence": "<HIGH | MEDIUM | LOW>",
  "key_signal": "<the most distinctive visual element that determined your choice>",
  "header_restart": <true or false>
}}"""

        sem = asyncio.Semaphore(max_concurrent)

        async def classify_one(img: str, page_no: int) -> dict:
            async with sem:
                try:
                    response = await self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": [
                                {"type": "text", "text": user_prompt_template},
                                {"type": "image_url", "image_url": {
                                    "url": f"data:image/jpeg;base64,{img}",
                                    "detail": "high"
                                }}
                            ]}
                        ],
                        max_tokens=200,
                        response_format={"type": "json_object"},
                        temperature=0,
                    )
                    raw = self._safe_parse_json(response.choices[0].message.content)
                    doc_type      = raw.get("type", "UNKNOWN").strip().upper()
                    confidence    = raw.get("confidence", "MEDIUM")
                    key_signal    = raw.get("key_signal", "")
                    header_restart = raw.get("header_restart", True)

                    # Allow invented type names — AI may return a name not in DB
                    # for pages that don't match any configured document type.
                    # These will be saved as UnverifiedDocument for staff review.
                    # Sanitize: uppercase, replace spaces with underscores
                    if doc_type not in valid_names:
                        doc_type = doc_type.upper().replace(" ", "_").replace("-", "_")
                        # Strip any non-alphanumeric/underscore chars
                        import re as _re
                        doc_type = _re.sub(r"[^A-Z0-9_]", "", doc_type) or "UNCLASSIFIED"

                    print(
                        f"[ai_service] page {page_no}: {doc_type} "
                        f"restart={header_restart} ({confidence}) — {key_signal[:60]}"
                    )
                    return {
                        "page": page_no,
                        "type": doc_type,
                        "signals": {
                            "confidence": confidence,
                            "key_signal": key_signal,
                            "header_restart": bool(header_restart),
                        }
                    }
                except Exception as e:
                    print(f"[ai_service] page {page_no} classify error → UNCLASSIFIED: {e}")
                    return {
                        "page": page_no,
                        "type": "UNCLASSIFIED",
                        "signals": {"header_restart": True}
                    }

        results = await asyncio.gather(
            *[classify_one(images[i], i + 1) for i in range(len(images))],
            return_exceptions=True,
        )

        pages = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                print(f"[ai_service] page {i+1} gather error → UNCLASSIFIED: {r}")
                pages.append({"page": i + 1, "type": "UNCLASSIFIED", "signals": {"header_restart": True}})
            else:
                pages.append(r)
        return pages

    # ------------------------------------------------------------------
    # Phase 2 — Extract fields from a document instance (fully dynamic)
    # ------------------------------------------------------------------

    def _deduplicate_codes(self, codes) -> list:
        """
        Normalize, deduplicate and return codes as a clean list.
        Handles comma-separated strings, slash-separated pairs, and plain strings.
        """
        if codes is None:
            return None
        if isinstance(codes, str):
            codes = [codes]
        if not isinstance(codes, list):
            return None
        seen = set()
        result = []
        for code in codes:
            if not isinstance(code, str):
                continue
            for part in code.split(","):
                for c in part.split("/"):
                    c = c.strip()
                    if c and c not in seen:
                        seen.add(c)
                        result.append(c)
        return result if result else None

    # Medical code format validators
    # These filter out hallucinated values that don't match the expected code format.

    _CPT_RE  = None  # initialized lazily
    _ICD_RE  = None
    _JCODE_RE = None

    def _is_valid_cpt(self, code: str) -> bool:
        """
        CPT / HCPCS codes:
          - 5 numeric digits: 99213, 20610, 36415
          - Letter + 4 digits: J3590, J1740, G0463, A4550, Q5123, C9257
          - 4 digits + letter: 0237T
          - Letter + 3 digits + letter+digit: edge cases
        Rejects ICD-9 (e.g. 279.899) and plain text.
        """
        import re
        if not code or not isinstance(code, str):
            return False
        c = code.strip().upper()
        return bool(re.match(
            r'^([0-9]{5}[A-Z]?|[A-Z][0-9]{4}[A-Z0-9]?|[0-9]{4}[A-Z])$', c
        ))

    def _is_valid_icd(self, code: str) -> bool:
        """
        Valid ICD codes:
          ICD-10: any letter A-Z + 2+ digits (e.g. M25.50, F41.9, J84.9, Z79.899)
          ICD-9:  3 digits + optional .XX suffix (e.g. 733.00, 278.01)
        
        Rejects HCPCS J-codes (J + exactly 4 digits, e.g. J1200, J3590) — those
        are drug/medication billing codes, NOT diagnosis codes.
        Also rejects plain text (GTP, BL) and CPT codes (99213).
        """
        import re
        if not code or not isinstance(code, str):
            return False
        c = code.strip().upper()
        # Reject HCPCS J-codes: J + 4 digits (medication billing codes)
        if re.match(r'^J[0-9]{4}[A-Z0-9]?$', c):
            return False
        # ICD-10: any letter + 2+ digits
        if re.match(r'^[A-Z][0-9]{2}', c):
            return True
        # ICD-9: exactly 3 digits with optional .1-2 digit decimal
        if re.match(r'^[0-9]{3}(\.[0-9]{1,2})?$', c):
            return True
        return False
    def _code_prefix(self, code: str) -> str:
        """
        Grouping prefix for sequential hallucination detection.
        Strips the final trailing digit so that codes differing only in
        their last digit are grouped together.
          M25.561, M25.562, M25.569  →  "M25.56"  (same group)
          M25.50, M25.60, M25.70     →  "M25.5", "M25.6", "M25.7"  (different groups ✓)
        """
        import re as _re
        return _re.sub(r'\d$', '', code.strip())

    def _remove_sequential_runs(self, codes: list, max_per_prefix: int = 2) -> list:
        """
        Remove sequential hallucinations where the model lists many consecutive
        codes from the same sub-category (e.g. M25.561, M25.562, M25.563...).
        Real clinical selections rarely pick more than 2 codes with the same prefix.
        """
        if not codes:
            return codes
        from collections import defaultdict as _dd
        seen = _dd(int)
        result = []
        for code in codes:
            if not isinstance(code, str):
                continue
            pfx = self._code_prefix(code)
            seen[pfx] += 1
            if seen[pfx] <= max_per_prefix:
                result.append(code)
        removed = [c for c in codes if c not in result]
        if removed:
            print(f"[ai_service] removed sequential run: {removed}")
        return result

    def _filter_codes_by_type(self, codes: list, field_name: str) -> list:
        """
        Filter a list of codes to only include values matching the expected
        format for the given field name. Removes hallucinated codes.
        For ICD fields, also removes sequential code runs.
        """
        if not codes:
            return codes
        fn = field_name.lower()
        is_cpt = any(kw in fn for kw in ("cpt", "procedure", "billing", "service", "hcpcs"))
        is_icd = any(kw in fn for kw in ("icd", "diagnos", "condition", " dx"))

        if is_cpt:
            filtered = [c for c in codes if self._is_valid_cpt(c)]
        elif is_icd:
            filtered = [c for c in codes if self._is_valid_icd(c)]
            # Remove sequential hallucinations (e.g. M25.561, M25.562, M25.569...)
            filtered = self._remove_sequential_runs(filtered, max_per_prefix=2)
        else:
            filtered = codes

        removed_format = [c for c in codes if c not in filtered]
        if removed_format:
            print(f"[ai_service] filtered {field_name}: {removed_format}")
        return filtered

    def _classify_field_page(self, field_name: str) -> str:
        """
        Route a field to the page it belongs on in a multi-page medical form.
        Returns: "first", "last", or "any"

        Medical billing forms follow a consistent layout:
        - CPT codes / procedures / medications → first page (billing grid)
        - ICD codes / diagnoses               → last page  (diagnosis list)
        - Patient info (name, DOB, date, etc.)→ first page (patient header)
        """
        fn = field_name.lower()
        if any(kw in fn for kw in ("icd", "diagnos", "condition", " dx")):
            return "last"
        if any(kw in fn for kw in ("cpt", "procedure", "medication", "drug", "billing", "service")):
            return "first"
        if any(kw in fn for kw in ("name", "birth", "dob", "date", "patient", "gender",
                                    "address", "phone", "insurance", "provider", "copay", "balance")):
            return "first"
        return "any"

    async def _extract_page(
        self,
        page_img: str,
        fields_list: List[Dict],
        doc_type: str,
        type_context: str,
        page_role: str = "",
    ) -> Dict[str, Any]:
        """Extract the given fields from one page image."""
        if not fields_list:
            return {}

        field_lines = []
        for f in fields_list:
            fn = f.get("fieldName") or f.get("name") or ""
            ft = f.get("type") or f.get("fieldType") or "text"
            fd = f.get("description") or f.get("label") or ""
            if not fn:
                continue
            hints = [f"type={ft}"]
            if fd:
                hints.append(fd)
            hints_str = ', '.join(hints)
            field_lines.append(f'  "{fn}": null  // {hints_str}')

        fields_block = "\n".join(field_lines)
        empty_json = json.dumps(
            {(f.get("fieldName") or f.get("name", "")): None
             for f in fields_list if f.get("fieldName") or f.get("name")},
            indent=2
        )
        role_hint = f" This is the {page_role}." if page_role else ""
        context_line = f"Document context: {type_context}" if type_context else ""

        system_prompt = (
            "You are a visual ink-mark detector for medical forms. "
            "Your ONLY task is to find items where someone physically drew on "
            "the printed form with pen, pencil, highlighter, or any writing instrument. "
            "Return valid JSON only. No markdown."
        )

        user_prompt = f"""Look at this medical form image carefully.

TASK: Find every place where someone has drawn, written, or marked on the PRINTED form
using a pen, pencil, marker, or highlighter.

WHAT COUNTS AS A MARK (extract these):
  → A checkmark ✓ or tick drawn inside or next to a box
  → An X or cross × drawn inside or next to a box  
  → A circle or oval drawn around a code, word, or row
  → A line or underline drawn under text
  → A highlighter mark (color wash over text)
  → Handwritten text (anything written in ink/pencil — clearly different from printed font)
  → A dot, slash, or any ink touching a code
  → Strike-through: a line crossed through an item

WHAT DOES NOT COUNT (ignore these completely):
  → Printed text — codes and labels pre-printed on the form
  → Printed checkbox outlines □ with nothing inside
  → Printed lines, borders, or dividers on the form
  → Printed section headers like "A. OFFICE VISITS" or "H. DIAGNOSIS"

FIELDS TO FILL (extract the CODE or TEXT that has a mark near/on it):
{fields_block}

IMPORTANT:
- If a code has NO mark physically drawn on or next to it → do NOT include it
- Codes that appear in sequence (e.g. M25.50, M25.51, M25.52...) are printed options, not marks
- A real provider visit has 1-5 CPT codes marked and 2-6 ICD codes marked
- Maximum {{}}: 5 for CPT/procedure fields, 8 for ICD/diagnosis fields, 8 for others
- Each code appears at most once
- For text fields (name, date of birth): extract the handwritten value exactly

Return ONLY:
{empty_json}"""

        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{page_img}",
                        "detail": "high"
                    }}
                ]}
            ],
            max_tokens=400,
            response_format={"type": "json_object"},
            temperature=0,
        )
        return self._safe_parse_json(response.choices[0].message.content)

    async def _extract_fields(
        self,
        doc_type: str,
        page_range: str,
        images: List[str],
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract fields with smart field-to-page routing.

        Each field is sent only to the page it belongs on:
        - CPT/billing fields  → first page only (billing grid, sections A-G)
        - ICD/diagnosis fields→ last page only  (H. DIAGNOSIS list)
        - Patient info fields → first page only (handwritten header)
        - Unknown fields      → all pages, first non-null wins

        This prevents J-codes appearing in ICD fields and ICD codes in CPT fields.
        """
        start, end = map(int, page_range.split("-"))
        selected_images = images[start - 1: end]
        fields_list = schema.get("fields", [])
        type_context = (schema.get("description") or "").strip()

        if not fields_list:
            return {}

        num_pages = len(selected_images)

        if num_pages == 1:
            return await self._extract_page(
                selected_images[0], fields_list, doc_type, type_context
            )

        # Route fields to their correct page
        first_fields, last_fields, any_fields = [], [], []
        for f in fields_list:
            fn = f.get("fieldName") or f.get("name") or ""
            if not fn:
                continue
            t = self._classify_field_page(fn)
            if t == "first":
                first_fields.append(f)
            elif t == "last":
                last_fields.append(f)
            else:
                any_fields.append(f)

        page_roles = (
            ["front page (CPT billing grid, patient header)"] +
            ["middle page"] * (num_pages - 2) +
            ["back page (ICD-10 diagnosis list)"]
        ) if num_pages > 1 else [""]

        # Build parallel tasks
        tasks, task_keys = [], []
        if first_fields:
            tasks.append(self._extract_page(
                selected_images[0], first_fields, doc_type, type_context, page_roles[0]
            ))
            task_keys.append(("targeted", first_fields))

        if last_fields:
            tasks.append(self._extract_page(
                selected_images[-1], last_fields, doc_type, type_context, page_roles[-1]
            ))
            task_keys.append(("targeted", last_fields))

        if any_fields:
            for i, img in enumerate(selected_images):
                tasks.append(self._extract_page(
                    img, any_fields, doc_type, type_context, page_roles[i]
                ))
                task_keys.append(("any", any_fields))

        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assemble result
        result = {
            (f.get("fieldName") or f.get("name", "")): None
            for f in fields_list if f.get("fieldName") or f.get("name")
        }

        for task_result, (kind, task_fields) in zip(all_results, task_keys):
            if isinstance(task_result, Exception):
                continue
            for f in task_fields:
                fn = f.get("fieldName") or f.get("name") or ""
                if not fn:
                    continue
                ft = (f.get("type") or f.get("fieldType") or "text").lower()
                is_list = ft in ("array", "list") or any(
                    kw in fn.lower() for kw in ("codes", "diagnos", "medication", "procedure")
                )
                val = task_result.get(fn)
                if is_list:
                    existing = result.get(fn)
                    if isinstance(existing, list) and isinstance(val, list):
                        result[fn] = existing + val
                    elif val is not None:
                        result[fn] = val if isinstance(val, list) else [str(val)]
                else:
                    if result.get(fn) is None and val is not None:
                        result[fn] = val

        # Final deduplication + format validation
        for f in fields_list:
            fn = f.get("fieldName") or f.get("name") or ""
            if not fn or fn not in result:
                continue
            val = result[fn]
            if isinstance(val, list):
                deduped = self._deduplicate_codes(val) or []
                result[fn] = self._filter_codes_by_type(deduped, fn) or None

        return result


    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_document(
        self,
        file_content: bytes,
        filename: str,
        schemas: List[Dict],
        db: Session,
        document_id: int,
        progress_callback=None,
        check_cancelled_callback=None,
    ) -> Dict[str, Any]:

        # ── 0. HARD RESET ──────────────────────────────────────────────────
        db.query(UnverifiedDocument).filter(
            UnverifiedDocument.document_id == document_id
        ).delete()
        db.commit()

        # ── 1. CONVERT TO IMAGES ───────────────────────────────────────────
        if progress_callback:
            await progress_callback("Converting to images...", 10)

        images = await self._convert_to_images(file_content, filename)
        total_pages = len(images)

        # ── 2. SCHEMA PREP ─────────────────────────────────────────────────
        # schema_map: types WITH extraction fields → full field extraction
        schema_map: Dict[str, Dict] = {
            s["type_name"].strip().upper(): s
            for s in schemas
            if s.get("type_name") and s.get("fields")
        }

        # classifier_types: ALL types from DB (with or without fields)
        # Types without fields → classified → UnverifiedDocument (staff reviews)
        classifier_types: List[Dict[str, str]] = [
            {
                "name":        s["type_name"].strip().upper(),
                "description": (s.get("description") or "").strip(),
            }
            for s in schemas
            if s.get("type_name")
        ]

        if not classifier_types:
            raise ValueError(
                "No document types configured for this organisation. "
                "Add document types under Templates → Document Types."
            )

        print(
            f"[ai_service] document_id={document_id} | pages={total_pages} | "
            f"types={[t['name'] for t in classifier_types]} | "
            f"extractable={sorted(schema_map.keys())}"
        )

        # ── 3. CLASSIFY ALL PAGES IN PARALLEL ──────────────────────────────
        if progress_callback:
            await progress_callback("Classifying pages...", 20)

        pages = await self._classify_all_pages(images, classifier_types)

        # ── 4. NORMALISE (fill any gaps with UNKNOWN) ───────────────────────
        normalized = {p["page"]: p for p in pages}
        if len(normalized) != total_pages:
            missing = [i for i in range(1, total_pages + 1) if i not in normalized]
            print(f"[ai_service] WARNING: missing pages {missing} — padding UNKNOWN")
            for pg in missing:
                normalized[pg] = {"page": pg, "type": "UNKNOWN", "signals": {"header_restart": True}}

        ordered_pages = [normalized[i] for i in range(1, total_pages + 1)]

        # ── 5. GROUP INTO DOCUMENT INSTANCES ───────────────────────────────
        structure = self.build_document_instances(ordered_pages)

        type_summary = Counter(d["type"] for d in structure)
        print(f"[ai_service] {len(structure)} instances: {dict(type_summary)}")

        # ── 6. SPLIT: extractable vs unverified ────────────────────────────
        verified_docs   = [(i, d) for i, d in enumerate(structure, 1) if schema_map.get(d["type"])]
        unverified_docs = [(i, d) for i, d in enumerate(structure, 1) if not schema_map.get(d["type"])]

        # For unverified/invented types: run auto-extraction to capture marked items
        # even though there's no predefined template for them.
        if unverified_docs:
            unverified_sem = asyncio.Semaphore(8)

            async def _auto_extract(doc_item: dict) -> dict:
                """Extract marked/checked items from a page with no predefined schema."""
                doc_type   = doc_item["type"]
                page_range = doc_item["page_range"]
                start, end = map(int, page_range.split("-"))
                page_images = images[start - 1: end]

                async with unverified_sem:
                    try:
                        user_content = [{"type": "text", "text": f"""Examine this medical document page ({doc_type}).

Extract ALL items that are visually MARKED: checked ☑, circled, underlined,
crossed out, or have handwriting directly adjacent to them.
DO NOT extract printed items that have no visual mark.

Also extract any handwritten text fields (patient name, dates, amounts, notes).

Return JSON with descriptive keys inferred from the form labels:
{{
  "marked_items": ["code or item 1", "code or item 2", ...],
  "handwritten_fields": {{"field_label": "value", ...}},
  "document_summary": "one sentence describing what this page is"
}}"""}]
                        for img in page_images:
                            user_content.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{img}", "detail": "high"}
                            })

                        response = await self.client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {"role": "system", "content": "You are a medical document data extractor. Extract only visually marked items. Return valid JSON only."},
                                {"role": "user", "content": user_content}
                            ],
                            max_tokens=1024,
                            response_format={"type": "json_object"},
                            temperature=0,
                        )
                        return self._safe_parse_json(response.choices[0].message.content)
                    except Exception as e:
                        print(f"[ai_service] auto-extract error {doc_type} p{page_range}: {e}")
                        return {}

            auto_results = await asyncio.gather(
                *[_auto_extract(doc) for _, doc in unverified_docs],
                return_exceptions=True,
            )

            for (_, doc), result in zip(unverified_docs, auto_results):
                extracted = result if isinstance(result, dict) else {}
                db.add(UnverifiedDocument(
                    document_id=document_id,
                    suspected_type=doc["type"],
                    page_range=doc["page_range"],
                    extracted_data=extracted,
                    status="PENDING",
                ))
        else:
            pass  # no unverified docs

        db.commit()

        # ── 7. EXTRACT FIELDS — all in parallel ────────────────────────────
        findings: List[Dict[str, Any]] = []

        if verified_docs:
            if progress_callback:
                await progress_callback(f"Extracting {len(verified_docs)} document(s)...", 50)

            if check_cancelled_callback and await check_cancelled_callback():
                raise Exception("Analysis Cancelled")

            extract_sem = asyncio.Semaphore(8)

            async def _extract_one(doc_item: dict, schema: dict) -> dict:
                doc_type   = doc_item["type"]
                page_range = doc_item["page_range"]
                async with extract_sem:
                    try:
                        raw_data = await self._extract_fields(
                            doc_type, page_range, images, schema
                        )
                        # Wrap in {"fields": ...} — document_service reads finding["data"]["fields"]
                        return {
                            "type": doc_type,
                            "page_range": page_range,
                            "data": {"fields": raw_data},
                            "confidence": 1.0,
                        }
                    except Exception as exc:
                        print(f"[ai_service] extraction error {doc_type} p{page_range}: {exc}")
                        return {
                            "type": doc_type,
                            "page_range": page_range,
                            "data": {"_error": str(exc), "fields": {}},
                            "confidence": 0.0,
                        }

            all_results = await asyncio.gather(
                *[_extract_one(doc, schema_map[doc["type"]]) for _, doc in verified_docs],
                return_exceptions=True,
            )
            for r in all_results:
                if isinstance(r, Exception):
                    print(f"[ai_service] unexpected gather error: {r}")
                else:
                    findings.append(r)

        # ── 8. FINALIZE ─────────────────────────────────────────────────────
        derived = Counter(
            r.suspected_type
            for r in db.query(UnverifiedDocument)
                        .filter(UnverifiedDocument.document_id == document_id)
                        .all()
        )
        db.commit()

        if progress_callback:
            await progress_callback("Finalizing...", 95)

        print(
            f"[ai_service] DONE document_id={document_id} | "
            f"extracted={len(findings)} | unverified={dict(derived)}"
        )

        return {
            "derived_documents": dict(derived),
            "findings": findings,
        }


ai_service = AIService()
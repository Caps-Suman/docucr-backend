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
                lambda: convert_from_bytes(file_content, dpi=150)
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
        A new instance starts when:
          - the type changes, OR
          - same type but header_restart=True (new patient header detected on this page)
        Pages with header_restart=False and same type as previous → merged into one instance.
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

            type_changed = page["type"] != current["type"]
            new_header   = page.get("signals", {}).get("header_restart", True)

            if type_changed or new_header:
                documents.append(current)
                current = {
                    "type": page["type"],
                    "start": page["page"],
                    "end": page["page"],
                }
            else:
                # Same type + continuation → extend current instance
                current["end"] = page["page"]

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
   - Use ALL_CAPS with underscores (e.g. DXA_ORDER, INSURANCE_CARD, LAB_REPORT, REFERRAL_LETTER)
   - Make the name describe what the document actually is, not what it contains
   - Common examples: DXA_DIAGNOSTIC_CODES, INSURANCE_CARD, FINANCIAL_RESPONSIBILITY,
     LAB_RESULTS, REFERRAL_FORM, CONSENT_FORM, PRIOR_AUTH, PATIENT_INTAKE
   - Do NOT use UNKNOWN — always invent a meaningful name

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
  • Back page of a DXA order showing more diagnosis categories (no patient name)
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
                    print(f"[ai_service] page {page_no} classify error → UNKNOWN: {e}")
                    return {
                        "page": page_no,
                        "type": "UNKNOWN",
                        "signals": {"header_restart": True}
                    }

        results = await asyncio.gather(
            *[classify_one(images[i], i + 1) for i in range(len(images))],
            return_exceptions=True,
        )

        pages = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                print(f"[ai_service] page {i+1} gather error → UNKNOWN: {r}")
                pages.append({"page": i + 1, "type": "UNKNOWN", "signals": {"header_restart": True}})
            else:
                pages.append(r)
        return pages

    # ------------------------------------------------------------------
    # Phase 2 — Extract fields from a document instance (fully dynamic)
    # ------------------------------------------------------------------

    async def _extract_fields(
        self,
        doc_type: str,
        page_range: str,
        images: List[str],
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:

        start, end = map(int, page_range.split("-"))
        selected_images = images[start - 1: end]

        fields_list = schema.get("fields", [])
        field_lines = []
        for f in fields_list:
            fn = f.get("fieldName") or f.get("name") or ""
            ft = f.get("type") or f.get("fieldType") or "text"
            fd = f.get("description") or f.get("label") or ""
            ex = f.get("exampleValue") or ""
            if not fn:
                continue
            hints = [f"type={ft}"]
            if fd:
                hints.append(fd)
            if ex:
                hints.append(f'e.g. "{ex}"')
            field_lines.append(f'  "{fn}": null  // {", ".join(hints)}')

        fields_block = "\n".join(field_lines)
        empty_json   = json.dumps(
            {(f.get("fieldName") or f.get("name", "")): None for f in fields_list if f.get("fieldName") or f.get("name")},
            indent=2
        )

        # Use the DB description for context if available
        type_context = (schema.get("description") or "").strip()
        context_line = f"Document description: {type_context}" if type_context else ""

        system_prompt = (
            f"You are extracting structured data from a {doc_type} document. "
            f"{context_line} "
            "Return valid JSON only. No markdown."
        )

        user_prompt = f"""Extract the requested fields from these medical document image(s).
All {len(selected_images)} image(s) belong to the same document — treat them as one continuous document.

FIELDS TO EXTRACT:
{fields_block}

CRITICAL EXTRACTION RULES:
1. MARKED ITEMS ONLY — This document is a FORM with checkboxes, circles, and handwriting.
   Extract ONLY items that are visually SELECTED: checked ☑, circled, underlined,
   crossed out, or have handwriting directly adjacent to them.
   DO NOT extract items that are merely printed on the form but have NO mark next to them.
   A blank checkbox □ = NOT selected. A checked checkbox ☑ or circled item = selected.

2. For CODE fields (CPT codes, ICD codes, billing codes):
   - Include ONLY codes that have a visible mark, check, circle, or handwritten annotation
   - The form prints many codes as options — ignore all unselected ones
   - Typical superbill: only 2-8 codes are actually selected out of hundreds printed

3. For TEXT fields (patient name, date of birth, dates, amounts):
   - Extract the handwritten or typed value exactly as it appears
   - Use null if the field is blank

4. For list fields: return a compact JSON array of strings
5. Extract ONLY the fields listed above — do NOT add extra keys
6. Preserve exact values (dates as written, codes as printed)

Return ONLY this JSON (no markdown):
{empty_json}"""

        user_content: List[Dict] = [{"type": "text", "text": user_prompt}]
        for img in selected_images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img}", "detail": "high"}
            })

        response = await self.client.chat.completions.create(
            model="gpt-4o",   # gpt-4o required for reliable checkbox detection
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            max_tokens=1024,  # compact output — only marked items, not all codes
            response_format={"type": "json_object"},
            temperature=0,
        )
        return self._safe_parse_json(response.choices[0].message.content)

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
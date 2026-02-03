from app.core.database import SessionLocal
from app.models.sop import SOP
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

def is_icd(code: str) -> bool:
    """
    Very strict ICD detector.
    ICD-10 starts with a letter + numbers (e.g., M17.0, Z00.00)
    """
    if not code or not isinstance(code, str):
        return False
    return code[0].isalpha() and "." in code


def migrate():
    db: Session = SessionLocal()
    try:
        sops = db.query(SOP).all()
        updated = 0

        for sop in sops:
            legacy = sop.coding_rules or []

            # Skip if already migrated
            if sop.coding_rules_cpt or sop.coding_rules_icd:
                continue

            cpt_rules = []
            icd_rules = []

            for rule in legacy:
                if not isinstance(rule, dict):
                    continue

                cpt = rule.get("cptCode")
                icd = rule.get("icdCode")  # future-proof

                if icd or (not cpt and rule.get("description")):
                    icd_rules.append({
                        "icdCode": icd or "",
                        "description": rule.get("description", ""),
                        "notes": rule.get("modifier", "")
                    })
                else:
                    cpt_rules.append(rule)

            sop.coding_rules_cpt = cpt_rules or []
            sop.coding_rules_icd = icd_rules or []

            flag_modified(sop, "coding_rules_cpt")
            flag_modified(sop, "coding_rules_icd")

            updated += 1

        db.commit()
        print(f"✅ Migration completed. Updated {updated} SOPs.")

    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()

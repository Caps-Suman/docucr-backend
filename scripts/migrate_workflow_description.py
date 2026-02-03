from app.core.database import SessionLocal
from app.models.sop import SOP  # adjust import
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

def migrate():
    db: Session = SessionLocal()
    try:
        sops = db.query(SOP).all()

        updated = 0
        for sop in sops:
            wp = sop.workflow_process or {}

            desc = wp.get("description")
            portals = wp.get("eligibility_verification_portals", [])

            if portals:
                description += "\n\nEligibility Verification Portals:\n"
                for p in portals:
                    description += f"- {p}\n"
            if (
                isinstance(wp, dict)
                and (not desc or not str(desc).strip())
                and wp.get("superbill_source")
            ):
                wp["description"] = wp["superbill_source"]
                sop.workflow_process = wp

                flag_modified(sop, "workflow_process")  # 🔥 THIS IS THE KEY
                updated += 1


        db.commit()
        print(f"✅ Migration complete. Updated {updated} SOPs.")

    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate()

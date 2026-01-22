from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, cast, String, select
from app.models.document import Document
from app.models.extracted_document import ExtractedDocument
from app.models.unverified_document import UnverifiedDocument
from app.models.status import Status
from app.models.document_type import DocumentType
from app.models.user_client import UserClient
from app.models.document_form_data import DocumentFormData
from datetime import datetime, timedelta
from typing import Dict, List, Any

class DashboardService:
    @staticmethod
    def get_admin_stats(db: Session) -> Dict[str, Any]:
        # 1. KPIs
        total_throughput = db.query(func.count(Document.id)).scalar() or 0
        
        # STP Rate: Completed documents with NO unverified records
        total_completed = db.query(func.count(Document.id)).join(Status).filter(Status.code == "COMPLETED").scalar() or 0
        stp_docs = db.query(func.count(Document.id)).join(Status).filter(
            Status.code == "COMPLETED",
            ~Document.id.in_(db.query(UnverifiedDocument.document_id))
        ).scalar() or 0
        
        stp_rate = (stp_docs / total_completed * 100) if total_completed > 0 else 0
        
        # System Confidence
        avg_confidence = db.query(func.avg(ExtractedDocument.confidence)).scalar() or 0
        
        # Storage Usage
        total_storage = db.query(func.sum(Document.file_size)).scalar() or 0
        
        # 2. Visualizations
        # Processing Trend (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        trend_data = db.query(
            func.date(Document.created_at).label("date"),
            func.count(Document.id).label("count")
        ).filter(Document.created_at >= thirty_days_ago)\
         .group_by(func.date(Document.created_at))\
         .order_by(func.date(Document.created_at)).all()
        
        # Verification Ratio
        needs_review_docs = db.query(func.count(Document.id)).join(Status).filter(Status.code == "NEEDS_REVIEW").scalar() or 0
        
        # Distribution by Document Type
        type_distribution = db.query(
            DocumentType.name,
            func.count(Document.id)
        ).join(Document, Document.document_type_id == DocumentType.id)\
         .group_by(DocumentType.name).all()
         
        # Status Distribution
        status_distribution = db.query(
            Status.code,
            func.count(Document.id)
        ).join(Document, Document.status_id == Status.id)\
         .group_by(Status.code).all()

        return {
            "kpis": {
                "totalThroughput": total_throughput,
                "stpRate": round(stp_rate, 1),
                "avgConfidence": round(avg_confidence * 100, 1),
                "totalStorage": total_storage
            },
            "charts": {
                "trend": [{"date": str(d.date), "count": d.count} for d in trend_data],
                "verificationRatio": {
                    "automated": stp_docs,
                    "manual": total_completed - stp_docs
                },
                "statusDistribution": {code: count for code, count in status_distribution},
                "typeDistribution": {name: count for name, count in type_distribution}
            }
        }

    @staticmethod
    def get_user_stats(db: Session, user_id: str) -> Dict[str, Any]:
        # Filter logic similar to document_service.py for role-based access
        # For simplicity in first pass, we focus on documents uploaded by user or assigned via clients
        
        # assigned_client_ids = db.query(UserClient.client_id).filter(
        #     UserClient.user_id == user_id
        # ).subquery()
        assigned_client_ids = select(UserClient.client_id).where(
            UserClient.user_id == user_id
        )
        
        client_doc_ids = db.query(Document.id).join(
            DocumentFormData, Document.id == DocumentFormData.document_id
        ).filter(
            DocumentFormData.data["client_id"].astext.in_(db.query(cast(UserClient.client_id, String)))
        ).subquery()
        
        base_query = db.query(Document).filter(
            or_(
                Document.user_id == user_id,
                Document.id.in_(client_doc_ids)
            )
        )
        
        total_assigned = base_query.count()
        pending_review = base_query.join(Status).filter(Status.code == "NEEDS_REVIEW").count()
        
        # User Specific Accuracy (Verified vs Rejected in UnverifiedDocuments)
        user_unverified = db.query(UnverifiedDocument).join(Document).filter(
            Document.user_id == user_id
        )
        verified_count = user_unverified.filter(UnverifiedDocument.status == "VERIFIED").count()
        rejected_count = user_unverified.filter(UnverifiedDocument.status == "REJECTED").count()
        total_unverified = verified_count + rejected_count
        accuracy = (verified_count / total_unverified * 100) if total_unverified > 0 else 0
        
        # Recent Activity
        recent_docs = base_query.order_by(Document.updated_at.desc()).limit(10).all()

        return {
            "kpis": {
                "totalAssigned": total_assigned,
                "pendingReview": pending_review,
                "accuracyRate": round(accuracy, 1),
                "completedToday": base_query.join(Status).filter(
                    Status.code == "COMPLETED",
                    Document.updated_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                ).count()
            },
            "recentActivity": [
                {
                    "id": d.id,
                    "filename": d.original_filename,
                    "status": d.status.code if d.status else "UNKNOWN",
                    "updatedAt": d.updated_at.isoformat()
                } for d in recent_docs
            ]
        }

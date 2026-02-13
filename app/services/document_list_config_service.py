from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from ..models.document_list_config import DocumentListConfig
from ..models.user import User

class DocumentListConfigService:
    
    
    @staticmethod
    def get_org_config(db: Session, organisation_id: str) -> Optional[Dict[str, Any]]:
        """Get organisation's document list configuration"""
        if not organisation_id:
            return None
            
        config = db.query(DocumentListConfig).filter(
            DocumentListConfig.organisation_id == organisation_id
        ).first()
        
        return config.configuration if config else None

    @staticmethod
    def get_config(db: Session) -> Optional[Dict[str, Any]]:
        """Get document list configuration (Legacy/unused??)"""
        config = db.query(DocumentListConfig).first()
        
        return config.configuration if config else None
    
    @staticmethod
    def save_org_config(db: Session, organisation_id: str, configuration: Dict[str, Any], user_id: str = None) -> Dict[str, Any]:
        """Save or update organisation's document list configuration"""
        if not organisation_id:
            raise ValueError("Organisation ID is required")
            
        config = db.query(DocumentListConfig).filter(
            DocumentListConfig.organisation_id == organisation_id
        ).first()
        
        if config:
            config.configuration = configuration
            # optional: track last updated by user
            if user_id:
                config.user_id = user_id
        else:
            config = DocumentListConfig(
                organisation_id=organisation_id,
                user_id=user_id, # Optional, acts as "last updated by"
                configuration=configuration
            )
            db.add(config)
            
        db.commit()
        db.refresh(config)
        
        return config.configuration
    
    @staticmethod
    def delete_org_config(db: Session, organisation_id: str) -> bool:
        """Delete organisation's document list configuration"""
        config = db.query(DocumentListConfig).filter(
            DocumentListConfig.organisation_id == organisation_id
        ).first()
        
        if config:
            db.delete(config)
            db.commit()
            return True
            
        return False
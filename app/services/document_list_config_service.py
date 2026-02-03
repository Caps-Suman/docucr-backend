from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from ..models.document_list_config import DocumentListConfig
from ..models.user import User

class DocumentListConfigService:
    
    
    @staticmethod
    def get_user_config(db: Session, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's document list configuration"""
        config = db.query(DocumentListConfig).filter(
            DocumentListConfig.user_id == user_id
        ).first()
        
        return config.configuration if config else None

    @staticmethod
    def get_config(db: Session) -> Optional[Dict[str, Any]]:
        """Get document list configuration"""
        config = db.query(DocumentListConfig).first()
        
        return config.configuration if config else None
    
    @staticmethod
    def save_user_config(db: Session, user_id: str, configuration: Dict[str, Any]) -> Dict[str, Any]:
        """Save or update user's document list configuration"""
        config = db.query(DocumentListConfig).filter(
            DocumentListConfig.user_id == user_id
        ).first()
        
        if config:
            config.configuration = configuration
        else:
            config = DocumentListConfig(
                user_id=user_id,
                configuration=configuration
            )
            db.add(config)
            
        db.commit()
        db.refresh(config)
        
        return config.configuration
    
    @staticmethod
    def delete_user_config(db: Session, user_id: str) -> bool:
        """Delete user's document list configuration"""
        config = db.query(DocumentListConfig).filter(
            DocumentListConfig.user_id == user_id
        ).first()
        
        if config:
            db.delete(config)
            db.commit()
            return True
            
        return False
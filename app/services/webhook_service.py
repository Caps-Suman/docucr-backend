import requests
import json
import asyncio
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from ..models.webhook import Webhook
from datetime import datetime

class WebhookService:
    @staticmethod
    def get_user_webhooks(db: Session, user_id: str) -> List[Webhook]:
        return db.query(Webhook).filter(Webhook.user_id == user_id).all()

    @staticmethod
    def create_webhook(db: Session, user_id: str, data: Dict[str, Any]) -> Webhook:
        webhook = Webhook(
            user_id=user_id,
            name=data.get('name'),
            url=data.get('url'),
            secret=data.get('secret'),
            events=data.get('events', []),
            is_active=data.get('is_active', True)
        )
        db.add(webhook)
        db.commit()
        db.refresh(webhook)
        return webhook

    @staticmethod
    def update_webhook(db: Session, webhook_id: str, user_id: str, data: Dict[str, Any]) -> Optional[Webhook]:
        webhook = db.query(Webhook).filter(Webhook.id == webhook_id, Webhook.user_id == user_id).first()
        if not webhook:
            return None
        
        if 'name' in data: webhook.name = data['name']
        if 'url' in data: webhook.url = data['url']
        if 'secret' in data: webhook.secret = data['secret']
        if 'events' in data: webhook.events = data['events']
        if 'is_active' in data: webhook.is_active = data['is_active']
        
        db.commit()
        db.refresh(webhook)
        return webhook

    @staticmethod
    def delete_webhook(db: Session, webhook_id: str, user_id: str) -> bool:
        webhook = db.query(Webhook).filter(Webhook.id == webhook_id, Webhook.user_id == user_id).first()
        if not webhook:
            return False
        
        db.delete(webhook)
        db.commit()
        return True

    @staticmethod
    def trigger_webhook_background(event_type: str, payload: Dict[str, Any], user_id: str, db_session_factory):
        """
        Triggers webhooks in the background. 
        Note: Needs a session factory because it might run in a separate thread/task.
        """
        db = db_session_factory()
        try:
            webhooks = db.query(Webhook).filter(
                Webhook.user_id == user_id,
                Webhook.is_active == True
            ).all()
            
            for webhook in webhooks:
                if event_type in webhook.events or '*' in webhook.events:
                    # Fire and forget request
                    try:
                        headers = {'Content-Type': 'application/json'}
                        # Potential enhancement: Add signature header if secret exists
                        
                        full_payload = {
                            "event": event_type,
                            "timestamp": datetime.utcnow().isoformat(),
                            "data": payload
                        }
                        
                        requests.post(
                            webhook.url, 
                            data=json.dumps(full_payload), 
                            headers=headers,
                            timeout=5
                        )
                    except Exception as e:
                        print(f"Failed to trigger webhook {webhook.url}: {str(e)}")
        finally:
            db.close()

webhook_service = WebhookService()

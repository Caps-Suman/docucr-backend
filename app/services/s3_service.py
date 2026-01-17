import boto3
import os
from typing import BinaryIO, Optional
from botocore.exceptions import ClientError
import asyncio
import uuid

class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
        self.bucket_name = os.getenv('AWS_S3_BUCKET')
    
    async def upload_file(self, file_obj: BinaryIO, filename: str, content_type: str, progress_callback=None) -> tuple[str, str]:
        """Upload file to S3 and return (s3_key, bucket_name)"""
        try:
            # Generate unique S3 key
            file_extension = filename.split('.')[-1] if '.' in filename else ''
            s3_key = f"documents/{uuid.uuid4()}.{file_extension}" if file_extension else f"documents/{uuid.uuid4()}"
            
            # Upload file in thread pool to avoid blocking asyncio loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.upload_fileobj(
                    file_obj,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={'ContentType': content_type},
                    Callback=progress_callback
                )
            )
            
            return s3_key, self.bucket_name
            
        except ClientError as e:
            raise Exception(f"Failed to upload file to S3: {str(e)}")
    
    async def delete_file(self, s3_key: str) -> bool:
        """Delete file from S3"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError:
            return False
    
    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """Generate presigned URL for file access"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
        except ClientError:
            return None

s3_service = S3Service()
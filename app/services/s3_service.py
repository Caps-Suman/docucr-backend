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
    
    async def upload_file(self, file_obj: BinaryIO, filename: str, content_type: str, progress_callback=None, s3_key: str = None) -> tuple[str, str]:
        """Upload file to S3 and return (s3_key, bucket_name)"""
        try:
            # Generate unique S3 key if not provided
            if not s3_key:
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
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            )
            return True
        except ClientError:
            return False

    async def download_file(self, s3_key: str) -> bytes:
        """Download file from S3"""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            )
            return await loop.run_in_executor(None, response['Body'].read)
        except ClientError as e:
            raise Exception(f"Failed to download file from S3: {str(e)}")

    async def get_file_stream(self, s3_key: str):
        """Get file stream from S3"""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            )
            return response
        except ClientError as e:
            raise Exception(f"Failed to get file stream from S3: {str(e)}")
    
    def generate_presigned_url(self, s3_key: str, expiration: int = 3600, response_content_disposition: str = None) -> Optional[str]:
        """Generate presigned URL for file access"""
        try:
            params = {'Bucket': self.bucket_name, 'Key': s3_key}
            if response_content_disposition:
                params['ResponseContentDisposition'] = response_content_disposition
                
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expiration
            )
            return url
        except ClientError:
            return None

s3_service = S3Service()
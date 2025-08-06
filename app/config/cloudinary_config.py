"""
Cloudinary configuration for image uploads
"""
import cloudinary
import cloudinary.uploader
import cloudinary.api
from typing import Optional, Dict, Any
import os
from fastapi import HTTPException, UploadFile
import uuid

# Configure Cloudinary
cloudinary.config(
    cloud_name="dvp7ejerb",
    api_key="651861558489477",
    api_secret="YsiIDuQxcQhHA3xKXjkLAZKUjbo",
    secure=True
)

class CloudinaryService:
    """Service for handling Cloudinary image operations"""
    
    @staticmethod
    def get_upload_options(folder: str = "products") -> Dict[str, Any]:
        """Get standard upload options for Cloudinary"""
        return {
            "folder": folder,
            "resource_type": "image",
            "format": "webp",  # Convert to WebP for better compression
            "quality": "auto:good",  # Automatic quality optimization
            "fetch_format": "auto",  # Automatic format selection
            "transformation": [
                {"width": 800, "height": 800, "crop": "limit"},  # Max size limit
                {"quality": "auto:good"}
            ]
        }
    
    @staticmethod
    async def upload_product_image(file: UploadFile, product_id: str) -> Dict[str, str]:
        """
        Upload a product image to Cloudinary
        
        Args:
            file: The uploaded file
            product_id: The product ID to use in the filename
            
        Returns:
            Dict containing image URLs and public_id
        """
        try:
            # Validate file type
            if not file.content_type or not file.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail="File must be an image")
            
            # Generate unique filename
            unique_filename = f"product_{product_id}_{uuid.uuid4().hex[:8]}"
            
            # Read file content
            file_content = await file.read()
            
            # Upload to Cloudinary
            upload_result = cloudinary.uploader.upload(
                file_content,
                public_id=unique_filename,
                **CloudinaryService.get_upload_options("products")
            )
            
            return {
                "public_id": upload_result["public_id"],
                "url": upload_result["secure_url"],
                "thumbnail_url": cloudinary.CloudinaryImage(upload_result["public_id"]).build_url(
                    width=200, height=200, crop="fill", quality="auto:good"
                ),
                "medium_url": cloudinary.CloudinaryImage(upload_result["public_id"]).build_url(
                    width=400, height=400, crop="limit", quality="auto:good"
                )
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")
    
    @staticmethod
    def delete_image(public_id: str) -> bool:
        """
        Delete an image from Cloudinary
        
        Args:
            public_id: The Cloudinary public ID of the image
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = cloudinary.uploader.destroy(public_id)
            return result.get("result") == "ok"
        except Exception as e:
            print(f"Failed to delete image {public_id}: {str(e)}")
            return False
    
    @staticmethod
    def get_image_urls(public_id: str) -> Dict[str, str]:
        """
        Get different sized URLs for an image
        
        Args:
            public_id: The Cloudinary public ID
            
        Returns:
            Dict containing different sized image URLs
        """
        if not public_id:
            return {}
        
        try:
            return {
                "url": cloudinary.CloudinaryImage(public_id).build_url(quality="auto:good"),
                "thumbnail_url": cloudinary.CloudinaryImage(public_id).build_url(
                    width=200, height=200, crop="fill", quality="auto:good"
                ),
                "medium_url": cloudinary.CloudinaryImage(public_id).build_url(
                    width=400, height=400, crop="limit", quality="auto:good"
                ),
                "large_url": cloudinary.CloudinaryImage(public_id).build_url(
                    width=800, height=800, crop="limit", quality="auto:good"
                )
            }
        except Exception as e:
            print(f"Failed to generate image URLs for {public_id}: {str(e)}")
            return {}

"""
AERIS AI OS - Cloud Computing Integration Service
Provides a cloud simulator for storage buckets (mimicking S3/Blob storage)
and virtual instance provisioning.
"""
import os
import shutil
import logging
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("aeris.services.cloud")


class CloudService:
    """Service simulating cloud infrastructure (Storage & Compute) locally."""

    def __init__(self):
        self.backend_dir = Path(__file__).resolve().parent.parent
        self.cloud_root = self.backend_dir / "data" / "cloud_simulator"
        self.cloud_root.mkdir(parents=True, exist_ok=True)
        
        # Default bucket
        (self.cloud_root / "aeris-default-bucket").mkdir(exist_ok=True)

    def storage_operation(self, action: str, file_path: str = "", bucket_name: str = "aeris-default-bucket", object_name: str = "") -> Dict[str, Any]:
        """
        Execute storage operations: create_bucket, upload_file, download_file, list_bucket, delete_file.
        """
        action = action.strip().lower()
        bucket_name = bucket_name.strip()
        bucket_dir = self.cloud_root / bucket_name

        try:
            # 1. Create Bucket
            if action == "create_bucket":
                bucket_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created cloud bucket: {bucket_name}")
                return {"success": True, "message": f"Cloud bucket '{bucket_name}' created/verified successfully."}

            # 2. List Bucket
            elif action == "list_bucket":
                if not bucket_dir.exists():
                    return {"success": False, "error": f"Bucket '{bucket_name}' does not exist."}
                files = []
                for f in bucket_dir.glob("*"):
                    if f.is_file():
                        stat = f.stat()
                        files.append({
                            "object_name": f.name,
                            "size_bytes": stat.st_size,
                            "uploaded_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        })
                return {"success": True, "bucket": bucket_name, "objects": files}

            # 3. Upload File
            elif action == "upload_file":
                if not bucket_dir.exists():
                    bucket_dir.mkdir(parents=True, exist_ok=True)
                
                src_path = Path(file_path)
                if not src_path.exists():
                    return {"success": False, "error": f"Local file not found: {file_path}"}
                
                obj_name = object_name or src_path.name
                dest_path = bucket_dir / obj_name
                
                shutil.copy(src_path, dest_path)
                logger.info(f"Uploaded {file_path} to cloud bucket {bucket_name} as {obj_name}")
                return {
                    "success": True,
                    "message": f"Successfully uploaded '{src_path.name}' to bucket '{bucket_name}' as '{obj_name}'.",
                    "cloud_uri": f"s3://{bucket_name}/{obj_name}"
                }

            # 4. Download File
            elif action == "download_file":
                if not bucket_dir.exists():
                    return {"success": False, "error": f"Bucket '{bucket_name}' does not exist."}
                
                if not object_name:
                    return {"success": False, "error": "object_name is required for downloading."}
                
                cloud_file = bucket_dir / object_name
                if not cloud_file.exists():
                    return {"success": False, "error": f"Object '{object_name}' not found in bucket '{bucket_name}'."}
                
                # If local file path is not provided, download to workspace
                if not file_path:
                    from config import settings
                    dest_dir = Path(settings.WORKSPACE_DIR) / "downloads"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest_path = dest_dir / object_name
                else:
                    dest_path = Path(file_path)
                    dest_path.parent.mkdir(parents=True, exist_ok=True)

                shutil.copy(cloud_file, dest_path)
                logger.info(f"Downloaded object {object_name} from {bucket_name} to {dest_path}")
                return {
                    "success": True,
                    "message": f"Successfully downloaded '{object_name}' from bucket '{bucket_name}' to local path '{dest_path}'.",
                    "local_path": str(dest_path)
                }

            # 5. Delete File
            elif action == "delete_file":
                if not bucket_dir.exists():
                    return {"success": False, "error": f"Bucket '{bucket_name}' does not exist."}
                
                if not object_name:
                    return {"success": False, "error": "object_name is required for deletion."}
                
                cloud_file = bucket_dir / object_name
                if not cloud_file.exists():
                    return {"success": False, "error": f"Object '{object_name}' not found in bucket '{bucket_name}'."}
                
                cloud_file.unlink()
                logger.info(f"Deleted object {object_name} from {bucket_name}")
                return {"success": True, "message": f"Successfully deleted '{object_name}' from bucket '{bucket_name}'."}

            else:
                return {"success": False, "error": f"Unknown storage action: '{action}'."}

        except Exception as e:
            logger.error(f"Cloud storage operation '{action}' failed: {e}")
            return {"success": False, "error": str(e)}

    def provision_instance(self, instance_type: str = "t3.micro", region: str = "us-east-1") -> Dict[str, Any]:
        """
        Simulate provisioning a cloud compute instance.
        """
        try:
            import random
            instance_id = f"i-{random.randint(100000000000, 999999999999):x}"
            ip_addr = f"54.{random.randint(10, 250)}.{random.randint(10, 250)}.{random.randint(10, 250)}"
            
            return {
                "success": True,
                "instance_id": instance_id,
                "instance_type": instance_type,
                "status": "running",
                "region": region,
                "public_ip": ip_addr,
                "provisioned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": f"Cloud VM Instance '{instance_id}' ({instance_type}) successfully provisioned and running in {region} at IP {ip_addr}."
            }
        except Exception as e:
            logger.error(f"Instance provisioning simulation failed: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
cloud_service = CloudService()

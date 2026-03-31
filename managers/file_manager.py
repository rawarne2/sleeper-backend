import json
import os
import tempfile
from datetime import datetime, UTC
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import NoCredentialsError, ClientError

from utils.helpers import setup_logging

logger = setup_logging()

class FileManager:
    """Handles file operations for JSON data storage and S3 uploads."""

    @staticmethod
    def get_data_directory() -> str:
        """Get the appropriate data directory path based on environment."""
        return '/app/data-files' if os.path.exists('/app') else './data-files'

    @staticmethod
    def create_descriptive_filename(league_format: str, is_redraft: bool, tep_level: Optional[str],
                                    operation_type: str = "refresh", include_timestamp: bool = True) -> str:
        """
        Create a more descriptive filename with additional context and options.

        Args:
            league_format: '1qb' or 'superflex'
            is_redraft: Whether this is redraft data
            tep_level: TEP configuration level
            operation_type: Type of operation ('refresh', 'export', 'backup', etc.)
            include_timestamp: Whether to include timestamp in filename

        Returns:
            Descriptive filename string
        """
        # Get current timestamp if requested
        timestamp = datetime.now(UTC).strftime(
            "%Y%m%d_%H%M%S") if include_timestamp else ""

        # More descriptive format type
        format_type = 'redraft' if is_redraft else 'dynasty'

        # More descriptive league format
        league_desc = 'superflex' if league_format == 'superflex' else '1qb'

        # Use raw TEP level
        tep_desc = tep_level if tep_level else "no_tep"

        # Build filename components
        components = ['ktc', operation_type,
                      league_desc, format_type, tep_desc]

        # Add timestamp if requested
        if timestamp:
            components.append(timestamp)

        # Create filename
        filename = f"{'_'.join(components)}.json"

        return filename

    @staticmethod
    def save_json_to_file(json_data: Dict[str, Any], filename: str) -> bool:
        """
        Save JSON data to a local file in the data-files directory.
        Only saves files if IS_DEV environment variable is set to 'true'.

        Args:
            json_data: Data to save as JSON
            filename: Target filename

        Returns:
            True if successful or skipped (not dev mode), False on error
        """
        # Check if we're in development mode
        is_dev = os.getenv('IS_DEV', '').lower() == 'true'

        if not is_dev:
            logger.info(
                "Skipping file save to data-files (not in dev mode): %s", filename)
            return True  # Return True since this is expected behavior in production

        try:
            data_dir = FileManager.get_data_directory()
            os.makedirs(data_dir, exist_ok=True)
            file_path = os.path.join(data_dir, filename)

            logger.info("Saving JSON data to %s...", file_path)
            with open(file_path, 'w') as json_file:
                json.dump(json_data, json_file, indent=2, default=str)

            logger.info("Successfully saved JSON data to %s", file_path)
            return True
        except Exception as e:
            logger.error("Error saving JSON to file: %s", e)
            return False

    @staticmethod
    def upload_json_to_s3(json_data: Dict[str, Any], bucket_name: str, object_key: str) -> bool:
        """
        Upload JSON data to an S3 bucket or access point.

        Args:
            json_data: Data to upload as JSON
            bucket_name: S3 bucket name or access point alias
            object_key: S3 object key (filename)

        Returns:
            True if successful, False otherwise
        """
        temp_file_path = None
        try:
            s3_client = boto3.client('s3')

            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                json.dump(json_data, temp_file, indent=2, default=str)
                temp_file_path = temp_file.name

            logger.info(
                f"Uploading JSON to s3://{bucket_name}/{object_key}...")

            # Upload to S3
            s3_client.upload_file(temp_file_path, bucket_name, object_key)
            logger.info(
                f"Successfully uploaded JSON to s3://{bucket_name}/{object_key}")

            return True

        except NoCredentialsError:
            logger.error(
                "AWS credentials not found. Make sure you've configured your AWS credentials.")
            return False
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get(
                'Error', {}).get('Message', 'Unknown error')
            logger.error(
                f"S3 ClientError - Code: {error_code}, Message: {error_message}")
            return False
        except Exception as e:
            logger.error("Unexpected error uploading to S3: %s", e)
            return False
        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")



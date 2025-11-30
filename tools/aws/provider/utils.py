import boto3
import json
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any, Union


class ParameterStoreManager:
    """AWS Parameter Store utility class for read/write operations with dict support"""
    
    def __init__(self, region_name: str = 'us-east-1'):
        self.ssm_client = boto3.client('ssm', region_name=region_name)
    
    def get_parameter(self, name: str, decrypt: bool = True, as_dict: bool = False) -> Optional[Union[str, Dict]]:
        """
        Get parameter value from Parameter Store
        
        Args:
            name: Parameter name
            decrypt: Whether to decrypt SecureString parameters
            as_dict: Whether to parse JSON string as dict
            
        Returns:
            Parameter value (string or dict) or None if not found
        """
        try:
            response = self.ssm_client.get_parameter(
                Name=name,
                WithDecryption=decrypt
            )
            value = response['Parameter']['Value']
            
            if as_dict:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return value
        except ClientError as e:
            if e.response['Error']['Code'] == 'ParameterNotFound':
                return None
            raise e
    
    def put_parameter(self, name: str, value: Union[str, Dict, Any], parameter_type: str = 'String', 
                     overwrite: bool = True, description: str = '') -> bool:
        """
        Put parameter to Parameter Store (supports dict objects)
        
        Args:
            name: Parameter name
            value: Parameter value (string, dict, or any JSON-serializable object)
            parameter_type: String, StringList, or SecureString
            overwrite: Whether to overwrite existing parameter
            description: Parameter description
            
        Returns:
            True if successful
        """
        try:
            # Convert dict/object to JSON string
            if isinstance(value, (dict, list)) or not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            
            self.ssm_client.put_parameter(
                Name=name,
                Value=value,
                Type=parameter_type,
                Overwrite=overwrite,
                Description=description
            )
            return True
        except (ClientError, json.JSONEncodeError):
            return False
    
    def delete_parameter(self, name: str) -> bool:
        """Delete parameter from Parameter Store"""
        try:
            self.ssm_client.delete_parameter(Name=name)
            return True
        except ClientError:
            return False

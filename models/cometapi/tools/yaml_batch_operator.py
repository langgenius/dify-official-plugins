
"""
Batch YAML Object Operator Tool
This script recursively searches YAML files and performs batch operations on specified objects/fields.
Supports nested object operations using dot notation (e.g., pricing, metadata.version).
Operation types: delete, add, modify, replace, remove
Supports complete operations for both object and array data types.

New features:
- Use relative paths for file matching, more flexible --include parameter
- Support multiple array operation modes (append, prepend, insert, by-value, by-index)
- Safe mandatory --include parameter requirement to prevent accidental batch modifications
- Automatic backup functionality with dry-run mode preview support
"""

import os
import sys
import yaml
import argparse
import fnmatch
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import shutil
from datetime import datetime
import json


class YAMLObjectOperator:
    """Handler for performing operations on objects in YAML files"""
    
    def __init__(self, dry_run: bool = False, backup: bool = True):
        self.dry_run = dry_run
        self.backup = backup
        self.processed_files = []
        self.modified_files = []
        self.errors = []
    
    def find_yaml_files(self, root_dir: Path, exclude_patterns: List[str] = None) -> List[Path]:
        """
        Recursively search for all YAML files
        """
        if exclude_patterns is None:
            exclude_patterns = ['_position.yaml', 'manifest.yaml', '*.backup']
        
        yaml_files = []
        
        for yaml_file in root_dir.rglob("*.yaml"):
            # Check exclude patterns
            if any(yaml_file.match(pattern) or yaml_file.name == pattern for pattern in exclude_patterns):
                continue
            
            # Verify it's a readable YAML file
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    yaml.safe_load(f)
                yaml_files.append(yaml_file)
            except Exception as e:
                self.errors.append(f"Warning: Unable to read {yaml_file}: {e}")
        
        return yaml_files
    
    def delete_nested_object(self, data: Dict[Any, Any], key_path: str) -> bool:
        """
        Delete nested object using dot notation
        Returns True if object was found and deleted
        """
        keys = key_path.split('.')
        current = data
        
        # Navigate to parent of target object
        for key in keys[:-1]:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        
        # Delete the target key
        target_key = keys[-1]
        if isinstance(current, dict) and target_key in current:
            del current[target_key]
            return True
        
        return False
    
    def add_nested_object(self, data: Dict[Any, Any], key_path: str, value: Any, array_mode: str = 'auto') -> bool:
        """
        Add nested object using dot notation
        array_mode: 'auto' (detect), 'append', 'prepend', 'insert:index', 'replace'
        Returns True if object was successfully added
        """
        keys = key_path.split('.')
        current = data
        
        # Navigate to parent, creating nested dicts as needed
        for key in keys[:-1]:
            if not isinstance(current, dict):
                return False
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Handle the target key
        target_key = keys[-1]
        if not isinstance(current, dict):
            return False
        
        # If auto mode, detect if target should be array or object
        if array_mode == 'auto':
            # Check if target already exists and is an array
            if target_key in current and isinstance(current[target_key], list):
                # Target is an array, append to it
                current[target_key].append(value)
                return True
            else:
                # Target is not an array, set as regular object
                current[target_key] = value
                return True
        
        # Handle specific array modes
        if array_mode == 'replace':
            current[target_key] = value
            return True
        
        # For other array modes, ensure target is an array
        if target_key not in current:
            current[target_key] = []
        
        if not isinstance(current[target_key], list):
            return False
        
        # Add element based on array mode
        if array_mode == 'append':
            current[target_key].append(value)
        elif array_mode == 'prepend':
            current[target_key].insert(0, value)
        elif array_mode == 'insert':
            # For insert mode, we need an index from the operation
            return False  # This should be handled by the caller
        else:
            return False
        
        return True
    
    def modify_nested_object(self, data: Dict[Any, Any], key_path: str, value: Any) -> bool:
        """
        Modify existing nested object using dot notation
        Returns True if object was found and modified
        """
        keys = key_path.split('.')
        current = data
        
        # Navigate to parent of target object
        for key in keys[:-1]:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        
        # Modify the target key only if it exists
        target_key = keys[-1]
        if isinstance(current, dict) and target_key in current:
            current[target_key] = value
            return True
        
        return False
    
    def get_nested_object(self, data: Dict[Any, Any], key_path: str) -> tuple[Any, bool]:
        """
        Get nested object using dot notation
        Returns (object, exists) tuple
        """
        keys = key_path.split('.')
        current = data
        
        # Navigate to target object
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return None, False
            current = current[key]
        
        return current, True
    
    def is_array_target(self, data: Dict[Any, Any], key_path: str) -> bool:
        """
        Check if the target object is an array
        """
        obj, exists = self.get_nested_object(data, key_path)
        return exists and isinstance(obj, list)

    def parse_value(self, value_str: str) -> Any:
        """
        Parse string value to appropriate type
        """
        if not value_str:
            return ""
        
        # Try to parse as JSON first (handles objects, arrays, etc.)
        try:
            return json.loads(value_str)
        except json.JSONDecodeError:
            # If not JSON, return as string
            return value_str
    
    def add_to_array(self, data: Dict[Any, Any], key_path: str, value: Any, mode: str = 'append') -> bool:
        """
        Add element to array using dot notation
        mode: 'append' (default), 'prepend', 'insert:index'
        Returns True if element was successfully added
        """
        keys = key_path.split('.')
        current = data
        
        # Navigate to parent of target array
        for key in keys[:-1]:
            if not isinstance(current, dict):
                return False
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Get the target array
        target_key = keys[-1]
        if not isinstance(current, dict):
            return False
        
        # Create array if it doesn't exist
        if target_key not in current:
            current[target_key] = []
        
        # Ensure target is an array
        if not isinstance(current[target_key], list):
            return False
        
        # Add element based on mode
        if mode == 'append':
            current[target_key].append(value)
        elif mode == 'prepend':
            current[target_key].insert(0, value)
        elif mode.startswith('insert:'):
            try:
                index = int(mode.split(':')[1])
                current[target_key].insert(index, value)
            except (ValueError, IndexError):
                return False
        else:
            return False
        
        return True
    
    def remove_from_array(self, data: Dict[Any, Any], key_path: str, value: Any = None, index: int = None) -> bool:
        """
        Remove element from array using dot notation
        Can remove by value or by index
        Returns True if element was successfully removed
        """
        keys = key_path.split('.')
        current = data
        
        # Navigate to parent of target array
        for key in keys[:-1]:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        
        # Get the target array
        target_key = keys[-1]
        if not isinstance(current, dict) or target_key not in current:
            return False
        
        if not isinstance(current[target_key], list):
            return False
        
        target_array = current[target_key]
        
        # Remove by index
        if index is not None:
            try:
                target_array.pop(index)
                return True
            except IndexError:
                return False
        
        # Remove by value
        if value is not None:
            try:
                target_array.remove(value)
                return True
            except ValueError:
                return False
        
        return False
    
    def modify_array_element(self, data: Dict[Any, Any], key_path: str, index: int, value: Any) -> bool:
        """
        Modify array element at specific index
        Returns True if element was successfully modified
        """
        keys = key_path.split('.')
        current = data
        
        # Navigate to parent of target array
        for key in keys[:-1]:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        
        # Get the target array
        target_key = keys[-1]
        if not isinstance(current, dict) or target_key not in current:
            return False
        
        if not isinstance(current[target_key], list):
            return False
        
        target_array = current[target_key]
        
        # Modify element at index
        try:
            target_array[index] = value
            return True
        except IndexError:
            return False
    
    def process_file(self, yaml_file: Path, operations: List[Dict[str, Any]]) -> bool:
        """
        Process a single YAML file to perform specified operations
        Returns True if file was modified
        """
        self.processed_files.append(yaml_file)
        
        try:
            # Load YAML content
            with open(yaml_file, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
            
            if not isinstance(content, dict):
                return False
            
            # Track if any modifications were made
            modified = False
            completed_operations = []
            
            # Perform each operation
            for operation in operations:
                op_type = operation['type']
                key_path = operation['key']
                value = operation.get('value')
                target_type = operation.get('target_type', 'auto')
                array_mode = operation.get('array_mode', 'append')
                index = operation.get('index')
                
                success = False
                op_description = ""
                
                if op_type == 'delete':
                    success = self.delete_nested_object(content, key_path)
                    op_description = f"delete {key_path}"
                
                elif op_type == 'add':
                    if target_type == 'object':
                        success = self.add_nested_object(content, key_path, value, 'replace')
                        op_description = f"add object {key_path}={value}"
                    elif target_type == 'array':
                        if array_mode == 'insert' and index is not None:
                            # Special handling for insert with index
                            keys = key_path.split('.')
                            current = content
                            for key in keys[:-1]:
                                if not isinstance(current, dict):
                                    success = False
                                    break
                                if key not in current:
                                    current[key] = {}
                                current = current[key]
                            else:
                                target_key = keys[-1]
                                if isinstance(current, dict):
                                    if target_key not in current:
                                        current[target_key] = []
                                    if isinstance(current[target_key], list):
                                        try:
                                            current[target_key].insert(index, value)
                                            success = True
                                        except IndexError:
                                            success = False
                            op_description = f"insert into array {key_path}[{index}]: {value}"
                        else:
                            success = self.add_nested_object(content, key_path, value, array_mode)
                            op_description = f"{array_mode} to array {key_path}: {value}"
                    else:  # auto
                        success = self.add_nested_object(content, key_path, value, 'auto')
                        op_description = f"add (auto-detect) {key_path}={value}"
                
                elif op_type == 'modify':
                    if target_type == 'array' and index is not None:
                        success = self.modify_array_element(content, key_path, index, value)
                        op_description = f"modify array {key_path}[{index}]={value}"
                    else:
                        success = self.modify_nested_object(content, key_path, value)
                        op_description = f"modify {key_path}={value}"
                
                elif op_type == 'replace':
                    success = self.add_nested_object(content, key_path, value, 'replace')
                    type_desc = "array" if target_type == 'array' else "object"
                    op_description = f"replace {type_desc} {key_path}={value}"
                
                elif op_type == 'remove':
                    if target_type == 'array':
                        if array_mode == 'by-value':
                            success = self.remove_from_array(content, key_path, value=value)
                            op_description = f"remove from array {key_path}: {value}"
                        elif array_mode == 'by-index' and index is not None:
                            success = self.remove_from_array(content, key_path, index=index)
                            op_description = f"remove from array {key_path}[{index}]"
                        else:
                            success = False
                    else:
                        success = self.delete_nested_object(content, key_path)
                        op_description = f"remove {key_path}"
                
                if success:
                    completed_operations.append(op_description)
                    modified = True
            
            # If no modifications, skip file
            if not modified:
                return False
            
            # In dry-run mode, just report what would be done
            if self.dry_run:
                print(f"[DRY RUN] Would perform on {yaml_file.relative_to(yaml_file.parents[3])}: {', '.join(completed_operations)}")
                return True
            
            # Create backup if enabled
            if self.backup:
                backup_file = yaml_file.with_suffix(f'.yaml.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}')
                shutil.copy2(yaml_file, backup_file)
            
            # Write modified content back to file with proper YAML formatting
            with open(yaml_file, 'w', encoding='utf-8') as f:
                yaml.dump(content, f, 
                         default_flow_style=False, 
                         allow_unicode=True, 
                         sort_keys=False,
                         indent=2,
                         width=float('inf'),  # Prevent line wrapping
                         default_style=None)
            
            self.modified_files.append(yaml_file)
            print(f"✓ Modified {yaml_file.relative_to(yaml_file.parents[3])}: {', '.join(completed_operations)}")
            
            return True
            
        except Exception as e:
            error_msg = f"Error processing {yaml_file}: {e}"
            self.errors.append(error_msg)
            print(f"✗ {error_msg}")
            return False
    
    def batch_operate(self, root_dir: Path, operations: List[Dict[str, Any]], include_patterns: List[str] = None, exclude_patterns: List[str] = None) -> None:
        """
        Batch perform operations on objects in YAML files
        """
        print(f"🔍 Scanning directory: {root_dir}")
        
        # Print operations summary
        op_summary = []
        for op in operations:
            op_type = op['type']
            key = op['key']
            value = op.get('value')
            if op_type == 'delete':
                op_summary.append(f"delete {key}")
            elif value is not None:
                op_summary.append(f"{op_type} {key}={value}")
            else:
                op_summary.append(f"{op_type} {key}")
        
        print(f"🎯 Operations to perform: {', '.join(op_summary)}")
        
        if self.dry_run:
            print("🧪 Running in DRY-RUN mode - no files will be modified")
        
        # Find all YAML files
        yaml_files = self.find_yaml_files(root_dir, exclude_patterns)
        
        # Filter by include patterns (now required)
        # Convert patterns to work with relative paths from root_dir
        filtered_files = []
        for yaml_file in yaml_files:
            # Get relative path from root_dir
            try:
                rel_path = yaml_file.relative_to(root_dir)
                # Check if any include pattern matches the relative path
                if any(fnmatch.fnmatch(str(rel_path), pattern) for pattern in include_patterns):
                    filtered_files.append(yaml_file)
            except ValueError:
                # File is not under root_dir, skip it
                continue
        yaml_files = filtered_files
        
        if not yaml_files:
            print("❌ No YAML files found matching criteria")
            return
        
        print(f"📄 Found {len(yaml_files)} YAML files to process")
        print()
        
        # Process each file
        for yaml_file in yaml_files:
            self.process_file(yaml_file, operations)
        
        # Print summary
        print()
        print("=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"Total files processed: {len(self.processed_files)}")
        print(f"Files modified: {len(self.modified_files)}")
        print(f"Errors encountered: {len(self.errors)}")
        
        if self.errors:
            print("\n⚠️  ERRORS:")
            for error in self.errors:
                print(f"  - {error}")
        
        if self.modified_files and not self.dry_run:
            print(f"\n✅ Successfully modified {len(self.modified_files)} files")
            if self.backup:
                print("💾 Backup files created with timestamp suffix")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Batch operations on objects in YAML files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    Examples:
      # Delete object - recommended usage
      python tools/yaml_batch_operator.py --operator delete --key pricing --dry-run --include "models/llm/openai/*.yaml"
      
      # Add object
      python tools/yaml_batch_operator.py --operator add --key pricing --value '{"input": "0.50", "output": "0.75"}' --type object --include "models/llm/anthropic/*.yaml"
      
      # Modify object
      python tools/yaml_batch_operator.py --operator modify --key pricing.input --value '"0.60"' --type object --include "models/llm/gemini/*.yaml"
        """
        )
    
    parser.add_argument(
        '--operator', '-o',
        action='append',
        choices=['delete', 'add', 'modify', 'replace', 'remove'],
        required=True,
        help='Operation to perform (can be used multiple times for different operations)'
    )
    
    parser.add_argument(
        '--key', '-k',
        action='append',
        required=True,
        help='Object keys to operate on (supports dot notation for nested objects, use multiple times to match --operator)'
    )
    
    parser.add_argument(
        '--value', '-v',
        action='append',
        help='Values for add/modify operations (JSON format supported, use multiple times to match --operator)'
    )
    
    parser.add_argument(
        '--type', '-t',
        action='append',
        choices=['object', 'array', 'auto'],
        default=None,
        help='Specify target type: object (key-value), array (list with -), or auto (detect). Use multiple times to match --operator'
    )
    
    parser.add_argument(
        '--array-mode',
        action='append',
        choices=['append', 'prepend', 'insert', 'by-value', 'by-index'],
        help='Array operation mode: append (end), prepend (start), insert (at index), by-value (remove), by-index (remove). Use multiple times to match --operator'
    )
    
    parser.add_argument(
        '--index', '-i',
        action='append',
        type=int,
        help='Index for array operations (use multiple times to match --operator)'
    )
    
    parser.add_argument(
        '--dir',
        type=str,
        default='.',
        help='Root directory to search (default: current directory)'
    )
    
    parser.add_argument(
        '--include',
        nargs='+',
        required=True,
        help='Only process files that match these patterns (using relative paths, such as "models/llm/openai/.yaml" or "openai/.yaml") - this parameter is required for security reasons'
    )
    
    parser.add_argument(
        '--exclude',
        nargs='+',
        default=['_position.yaml', 'manifest.yaml', '*.backup'],
        help='Exclude files matching these patterns'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )
    
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backup files'
    )
    
    parser.add_argument(
        '--verbose', '-b',
        action='store_true',
        help='Enable verbose output'
    )
    
    return parser.parse_args()


def validate_arguments(args):
    """Validate command line arguments"""
    # Check if directory exists
    root_dir = Path(args.dir)
    if not root_dir.exists():
        print(f"❌ Error: Directory '{args.dir}' does not exist")
        sys.exit(1)
    
    if not root_dir.is_dir():
        print(f"❌ Error: '{args.dir}' is not a directory")
        sys.exit(1)
    
    # Check that operator and key lists have compatible lengths
    num_operators = len(args.operator)
    num_keys = len(args.key)
    num_values = len(args.value) if args.value else 0
    num_types = len(args.type) if args.type else 0
    num_array_modes = len(args.array_mode) if args.array_mode else 0
    num_indices = len(args.index) if args.index else 0
    
    if num_operators != num_keys:
        print(f"❌ Error: Number of operators ({num_operators}) must match number of keys ({num_keys})")
        sys.exit(1)
    
    # Check if values are required for certain operations
    for i, op in enumerate(args.operator):
        if op in ['add', 'modify', 'replace', 'remove']:
            # For remove operation with array type, value might be required
            if op == 'remove':
                array_mode = args.array_mode[i] if args.array_mode and i < len(args.array_mode) else None
                if array_mode == 'by-value' and (not args.value or i >= len(args.value)):
                    print(f"❌ Error: Remove operation with 'by-value' mode requires a value for key '{args.key[i]}'")
                    sys.exit(1)
                elif array_mode == 'by-index' and (not args.index or i >= len(args.index)):
                    print(f"❌ Error: Remove operation with 'by-index' mode requires an index for key '{args.key[i]}'")
                    sys.exit(1)
            elif op in ['add', 'modify', 'replace']:
                if not args.value or i >= len(args.value) or not args.value[i]:
                    print(f"❌ Error: Operation '{op}' requires a value for key '{args.key[i]}'")
                    sys.exit(1)
    
    # Validate key format
    for key in args.key:
        if not key.strip():
            print(f"❌ Error: Empty key specified")
            sys.exit(1)
    
    return root_dir


def prepare_operations(args) -> List[Dict[str, Any]]:
    """Prepare operations list from arguments"""
    operations = []
    operator = YAMLObjectOperator()  # Temporary instance for value parsing
    
    for i, op_type in enumerate(args.operator):
        operation = {
            'type': op_type,
            'key': args.key[i]
        }
        
        # Add value for operations that need it
        if op_type in ['add', 'modify', 'replace'] and args.value and i < len(args.value):
            operation['value'] = operator.parse_value(args.value[i])
        elif op_type == 'remove':
            # For remove operation, value might be needed for by-value mode
            array_mode = args.array_mode[i] if args.array_mode and i < len(args.array_mode) else None
            if array_mode == 'by-value' and args.value and i < len(args.value):
                operation['value'] = operator.parse_value(args.value[i])
        
        # Add target type
        if args.type and i < len(args.type):
            operation['target_type'] = args.type[i]
        else:
            operation['target_type'] = 'auto'
        
        # Add array mode
        if args.array_mode and i < len(args.array_mode):
            operation['array_mode'] = args.array_mode[i]
        else:
            operation['array_mode'] = 'append'  # default
        
        # Add index for operations that need it
        if args.index and i < len(args.index):
            operation['index'] = args.index[i]
        
        operations.append(operation)
    
    return operations


def main():
    """Main function"""
    args = parse_arguments()
    root_dir = validate_arguments(args)
    
    # Prepare operations
    operations = prepare_operations(args)
    
    # Create operator instance
    operator = YAMLObjectOperator(
        dry_run=args.dry_run,
        backup=not args.no_backup
    )
    
    try:
        # Perform batch operations
        operator.batch_operate(
            root_dir=root_dir,
            operations=operations,
            include_patterns=args.include,
            exclude_patterns=args.exclude
        )
        
    except KeyboardInterrupt:
        print("\n⏹️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

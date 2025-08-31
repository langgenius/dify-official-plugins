
"""
Automatic _position.yaml generator
This script recursively searches for YAML model files and updates _position.yaml files
Automatically generates and updates _position.yaml files grouped by provider
"""

import os
import yaml
from pathlib import Path
from collections import defaultdict
import re


def find_yaml_files(root_dir):
    """
    Recursively search for all yaml files (excluding _position.yaml and other special files)
    """
    yaml_files = []
    root_path = Path(root_dir)
    
    for yaml_file in root_path.rglob("*.yaml"):
        # Skip special files
        if yaml_file.name.startswith('_') or yaml_file.name in ['manifest.yaml']:
            continue
            
        # Ensure this is a model configuration file (contains model field)
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
                if isinstance(content, dict) and 'model' in content:
                    # Check and fix filename if necessary
                    corrected_file = check_and_fix_filename(yaml_file)
                    yaml_files.append(corrected_file)
        except Exception as e:
            print(f"Warning: Unable to read file {yaml_file}: {e}")
            
    return yaml_files


def extract_provider_from_path(yaml_file, base_dir):
    """
    Extract provider name from file path
    Example: models/llm/openai/gpt-4.yaml -> openai
    """
    relative_path = yaml_file.relative_to(base_dir)
    parts = relative_path.parts
    
    # For files directly in provider directories like: openai/gpt-4.yaml
    if len(parts) >= 2:
        return parts[0]  # Provider name is the first directory
    
    return "unknown"


def check_and_fix_filename(yaml_file):
    """
    Check if YAML filename matches the model name in the file, and rename if necessary
    """
    try:
        with open(yaml_file, 'r', encoding='utf-8') as f:
            content = yaml.safe_load(f)
            model_name = content.get('model', '')
            
        if not model_name:
            print(f"Warning: No 'model' field found in {yaml_file}")
            return yaml_file
        
        # Get current filename without extension
        current_name = yaml_file.stem
        expected_name = model_name
        
        # Check if filename matches model name
        if current_name != expected_name:
            # Generate new filename
            new_filename = f"{expected_name}.yaml"
            new_file_path = yaml_file.parent / new_filename
            
            # Check if target file already exists
            if new_file_path.exists() and new_file_path != yaml_file:
                print(f"Error: Cannot rename {yaml_file.name} to {new_filename} - target file already exists")
                return yaml_file
            
            try:
                # Rename the file
                yaml_file.rename(new_file_path)
                print(f"Renamed: {yaml_file.name} -> {new_filename} (model: {model_name})")
                return new_file_path
            except Exception as e:
                print(f"Error renaming {yaml_file.name} to {new_filename}: {e}")
                return yaml_file
        
        return yaml_file
        
    except Exception as e:
        print(f"Error checking filename for {yaml_file}: {e}")
        return yaml_file


def load_model_info(yaml_file):
    """
    Load model file and extract basic information
    """
    try:
        with open(yaml_file, 'r', encoding='utf-8') as f:
            content = yaml.safe_load(f)
            return {
                'model': content.get('model', ''),
                'label': content.get('label', {}).get('en_US', content.get('model', '')),
                'model_type': content.get('model_type', 'llm'),
                'file_path': yaml_file
            }
    except Exception as e:
        print(f"Error loading {yaml_file}: {e}")
        return None


def group_models_by_provider(yaml_files, base_dir):
    """
    Group models by provider
    """
    provider_groups = defaultdict(list)
    
    for yaml_file in yaml_files:
        provider = extract_provider_from_path(yaml_file, base_dir)
        model_info = load_model_info(yaml_file)
        
        if model_info:
            provider_groups[provider].append(model_info)
    
    return provider_groups


def get_provider_display_name(provider):
    """
    Get display name for provider (just use the folder name as-is)
    """
    return provider


def generate_position_yaml_content(provider_groups):
    """
    Generate _position.yaml file content
    """
    lines = []
    
    # Sort by provider name
    sorted_providers = sorted(provider_groups.keys())
    
    for provider in sorted_providers:
        models = provider_groups[provider]
        if not models:
            continue
            
        # Add provider comment
        display_name = get_provider_display_name(provider)
        lines.append(f"# {display_name} models ({len(models)})")
        
        # Sort by model name
        sorted_models = sorted(models, key=lambda x: x['model'])
        
        for model in sorted_models:
            lines.append(f"- {model['model']}")
        
        lines.append("")  # Empty line separator
    
    # Remove last empty line
    if lines and lines[-1] == "":
        lines.pop()
        
    return "\n".join(lines) + "\n"


def update_position_yaml(model_type_dir, provider_groups):
    """
    Update _position.yaml file in specified directory
    """
    position_file = model_type_dir / "_position.yaml"
    
    if not provider_groups:
        print(f"No models found for {model_type_dir}")
        return
    
    content = generate_position_yaml_content(provider_groups)
    
    try:
        # Backup existing file
        if position_file.exists():
            backup_file = position_file.with_suffix('.yaml.backup')
            position_file.rename(backup_file)
            print(f"Backed up existing file to {backup_file}")
        
        # Write new content
        with open(position_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Updated {position_file}")
        print(f"Total models: {sum(len(models) for models in provider_groups.values())}")
        
    except Exception as e:
        print(f"Error updating {position_file}: {e}")


def main():
    """
    Main function: automatically update _position.yaml files
    """
    # Get parent directory of script directory (cometapi directory)
    script_dir = Path(__file__).parent
    cometapi_dir = script_dir.parent
    models_dir = cometapi_dir / "models"
    
    if not models_dir.exists():
        print(f"Models directory not found: {models_dir}")
        return
    
    print(f"Scanning models directory: {models_dir}")
    
    # Process by model type groups
    model_types = ['llm', 'text_embedding', 'rerank', 'tts', 'speech2text', 'moderation']
    
    for model_type in model_types:
        model_type_dir = models_dir / model_type
        if not model_type_dir.exists():
            continue
            
        print(f"\nProcessing {model_type} models...")
        
        # Search for all yaml files under this type and check/fix filenames
        yaml_files = []
        for yaml_file in model_type_dir.rglob("*.yaml"):
            if yaml_file.name.startswith('_') or yaml_file.name == 'manifest.yaml':
                continue
            
            # Check if it's a valid model file and fix filename if needed
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load(f)
                    if isinstance(content, dict) and 'model' in content:
                        # Check and fix filename
                        corrected_file = check_and_fix_filename(yaml_file)
                        yaml_files.append(corrected_file)
            except Exception as e:
                print(f"Warning: Unable to process file {yaml_file}: {e}")
        
        if not yaml_files:
            print(f"No YAML files found in {model_type_dir}")
            continue
        
        # Group by provider
        provider_groups = group_models_by_provider(yaml_files, model_type_dir)
        
        # Update _position.yaml
        update_position_yaml(model_type_dir, provider_groups)
    
    print("\n✅ _position.yaml files updated successfully!")


if __name__ == "__main__":
    main()

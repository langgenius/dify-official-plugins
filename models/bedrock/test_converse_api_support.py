#!/usr/bin/env python3
"""
Test script to verify Converse API support for Claude 4.5 Sonnet model.
This script validates that:
1. The model ID mapping is correct
2. The global prefix is properly configured in CONVERSE_API_ENABLED_MODEL_INFO
3. The model supports system prompts and tool use
"""

import sys
import os

# Add the parent directory to the path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.llm import model_ids
from models.llm.llm import BedrockLargeLanguageModel


def test_model_id_mapping():
    """Test that Claude 4.5 Sonnet has correct model ID mapping"""
    print("=" * 80)
    print("Test 1: Model ID Mapping")
    print("=" * 80)
    
    model_name = "Claude 4.5 Sonnet"
    model_type = "anthropic claude"
    
    model_id = model_ids.get_model_id(model_type, model_name)
    expected_id = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    
    print(f"Model Type: {model_type}")
    print(f"Model Name: {model_name}")
    print(f"Model ID: {model_id}")
    print(f"Expected ID: {expected_id}")
    
    if model_id == expected_id:
        print("✓ PASS: Model ID mapping is correct")
        return True
    else:
        print("✗ FAIL: Model ID mapping is incorrect")
        return False


def test_cross_region_support():
    """Test that Claude 4.5 Sonnet supports cross-region inference"""
    print("\n" + "=" * 80)
    print("Test 2: Cross-Region Support")
    print("=" * 80)
    
    model_id = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    
    is_supported = model_ids.is_support_cross_region(model_id)
    
    print(f"Model ID: {model_id}")
    print(f"Cross-Region Support: {is_supported}")
    
    if is_supported:
        print("✓ PASS: Model supports cross-region inference")
        return True
    else:
        print("✗ FAIL: Model does not support cross-region inference")
        return False


def test_global_prefix_configuration():
    """Test that global.anthropic.claude prefix is configured in Converse API"""
    print("\n" + "=" * 80)
    print("Test 3: Global Prefix Configuration")
    print("=" * 80)
    
    # Test standard model ID
    standard_model_id = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    standard_info = BedrockLargeLanguageModel._find_model_info(standard_model_id)
    
    print(f"Standard Model ID: {standard_model_id}")
    if standard_info:
        print(f"  - Found in Converse API config: Yes")
        print(f"  - Support System Prompts: {standard_info['support_system_prompts']}")
        print(f"  - Support Tool Use: {standard_info['support_tool_use']}")
    else:
        print(f"  - Found in Converse API config: No")
    
    # Test global inference profile ID
    global_model_id = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
    global_info = BedrockLargeLanguageModel._find_model_info(global_model_id)
    
    print(f"\nGlobal Model ID: {global_model_id}")
    if global_info:
        print(f"  - Found in Converse API config: Yes")
        print(f"  - Support System Prompts: {global_info['support_system_prompts']}")
        print(f"  - Support Tool Use: {global_info['support_tool_use']}")
    else:
        print(f"  - Found in Converse API config: No")
    
    # Verify both are found and have correct capabilities
    if standard_info and global_info:
        if (standard_info['support_system_prompts'] and 
            standard_info['support_tool_use'] and
            global_info['support_system_prompts'] and 
            global_info['support_tool_use']):
            print("\n✓ PASS: Both standard and global model IDs are properly configured")
            return True
        else:
            print("\n✗ FAIL: Model capabilities are not correctly configured")
            return False
    else:
        print("\n✗ FAIL: Model IDs not found in Converse API configuration")
        return False


def test_region_prefix_generation():
    """Test that global prefix is correctly generated for supported regions"""
    print("\n" + "=" * 80)
    print("Test 4: Region Prefix Generation")
    print("=" * 80)
    
    test_regions = [
        ('us-west-2', 'global'),
        ('us-east-1', 'global'),
        ('eu-west-1', 'global'),
        ('ap-northeast-1', 'global'),
    ]
    
    all_passed = True
    for region, expected_prefix in test_regions:
        actual_prefix = model_ids.get_region_area(region, prefer_global=True)
        status = "✓" if actual_prefix == expected_prefix else "✗"
        print(f"{status} Region: {region:20s} Expected: {expected_prefix:10s} Actual: {actual_prefix}")
        if actual_prefix != expected_prefix:
            all_passed = False
    
    if all_passed:
        print("\n✓ PASS: All region prefixes are correctly generated")
        return True
    else:
        print("\n✗ FAIL: Some region prefixes are incorrect")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("Claude 4.5 Sonnet Converse API Support Verification")
    print("=" * 80 + "\n")
    
    results = []
    
    # Run all tests
    results.append(("Model ID Mapping", test_model_id_mapping()))
    results.append(("Cross-Region Support", test_cross_region_support()))
    results.append(("Global Prefix Configuration", test_global_prefix_configuration()))
    results.append(("Region Prefix Generation", test_region_prefix_generation()))
    
    # Print summary
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! Claude 4.5 Sonnet is properly configured for Converse API.")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed. Please review the configuration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

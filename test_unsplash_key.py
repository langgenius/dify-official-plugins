#!/usr/bin/env python3
"""
Unsplash API Key 测试脚本
用于验证您的 API Key 是否有效
"""

import requests
import sys

def test_unsplash_key(api_key):
    """测试 Unsplash API Key"""
    print(f"🔍 测试 API Key: {api_key[:10]}...")
    
    # 测试搜索端点
    url = "https://api.unsplash.com/search/photos"
    headers = {
        "Authorization": f"Client-ID {api_key}",
        "Accept-Version": "v1"
    }
    params = {
        "query": "nature",
        "per_page": 1
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        print(f"📡 HTTP状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            total = data.get('total', 0)
            print(f"✅ API Key有效！找到 {total} 张图片")
            return True
        else:
            print(f"❌ API Key无效")
            try:
                error_data = response.json()
                print(f"错误详情: {error_data}")
            except:
                print(f"错误详情: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
        return False

if __name__ == "__main__":
    print("=== Unsplash API Key 验证工具 ===\n")
    
    # 您可以在这里直接输入您的API Key进行测试
    test_key = "HXbvf6fjkBUTX3hBrP9YYSnohZ90oHVufLTsv05asME"  # 替换为您的真实API Key
    
    if test_unsplash_key(test_key):
        print("\n🎉 您的API Key可以正常使用！")
    else:
        print("\n💡 解决方案：")
        print("1. 检查API Key是否正确复制")
        print("2. 确认API Key来自 https://unsplash.com/developers")
        print("3. 确保选择的是 'Access Key'，不是 'Secret Key'")
        print("4. 如果仍有问题，请重新生成API Key")
 
 
 
 
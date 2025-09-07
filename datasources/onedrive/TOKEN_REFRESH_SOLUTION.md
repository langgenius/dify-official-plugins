# OneDrive令牌过期解决方案

## 🚨 **问题确认：访问令牌过期**

基于调试日志：
```bash
DEBUG: Token expired, refreshing...
DEBUG: Token expired, refreshing...
```

**确认OneDrive访问令牌已过期**，这导致：
- OneDrive节点执行失败（显示红色🔴）
- 文档提取器显示"没有变量"
- Pipeline无法正常工作

## 🔧 **立即解决方案**

### 方案1：Dify界面重新授权（最简单）

#### 步骤1：删除现有OneDrive连接
```
Dify控制台操作：
1. 进入 设置 → 数据源提供商
2. 找到 OneDrive 配置
3. 点击 "删除" 或 "取消授权"
```

#### 步骤2：重新配置OneDrive
```
1. 点击 "添加数据源提供商"
2. 选择 OneDrive
3. 输入您的Azure应用信息：
   - Client ID: [您的Azure应用Client ID]
   - Client Secret: [您的Azure应用Client Secret]
```

#### 步骤3：重新授权
```
1. 点击 "授权" 按钮
2. 跳转到Microsoft登录页面
3. 登录您的OneDrive账户
4. 授权Dify访问OneDrive
5. 返回Dify完成配置
```

### 方案2：检查Azure应用配置

#### 验证Azure应用注册设置：
```
Azure门户检查项：
1. 应用ID（Client ID）是否正确
2. 客户端密钥（Client Secret）是否有效
3. 重定向URI是否正确配置
4. API权限是否包含必需权限：
   - Files.Read
   - Files.Read.All  
   - User.Read
   - offline_access
```

#### 如果需要重新创建Azure应用：
```
1. 访问 https://portal.azure.com
2. 进入 Azure Active Directory → 应用注册
3. 创建新的应用注册
4. 配置重定向URI为Dify的回调地址
5. 添加必需的API权限
6. 创建新的客户端密钥
```

### 方案3：手动测试令牌刷新（技术调试）

如果想验证令牌刷新机制：

```python
# 在OneDrive插件目录中运行
cd /Users/frederick/Documents/dify-official-plugins/datasources/onedrive
source venv/bin/activate

# 创建测试脚本
cat > test_token_refresh.py << 'EOF'
import requests

def test_token_refresh(client_id, client_secret, refresh_token):
    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "offline_access User.Read Files.Read Files.Read.All",
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    response = requests.post(token_url, data=token_data, headers=headers, timeout=15)
    
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.text}")
    
    if response.status_code == 200:
        token_json = response.json()
        print("✅ 令牌刷新成功")
        print(f"新Access Token前缀: {token_json.get('access_token', '')[:20]}...")
    else:
        print("❌ 令牌刷新失败")
        print("可能需要重新进行OAuth授权")

if __name__ == "__main__":
    # 请替换为实际值
    test_token_refresh(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET", 
        refresh_token="YOUR_REFRESH_TOKEN"
    )
EOF

# 运行测试（需要替换实际的凭证）
# python test_token_refresh.py
```

## 🎯 **推荐解决步骤**

### 最快速的解决方案：

1. **立即在Dify中重新授权OneDrive**：
   ```
   删除现有连接 → 重新添加 → 重新授权
   ```

2. **重新运行Pipeline**：
   ```
   确保OneDrive节点显示绿色✅
   文档提取器应该立即显示可用变量
   ```

3. **验证工作正常**：
   ```
   OneDrive节点：{{onedrive_docs.result}}
   文档提取器接收到文件数据
   Pipeline成功执行
   ```

## ⚠️ **预防措施**

### 避免未来令牌过期问题：

1. **定期使用OneDrive连接**：
   ```
   令牌通常90天过期
   定期运行Pipeline保持活跃状态
   ```

2. **监控认证状态**：
   ```
   在Pipeline中添加错误处理
   定期检查数据源连接状态
   ```

3. **备用认证方案**：
   ```
   考虑使用应用程序权限而非委托权限
   或设置自动刷新机制
   ```

## 🚀 **成功指标**

完成重新授权后，应该看到：

```
OneDrive节点状态：
🟢 绿色圆点 - 执行成功
📄 有输出数据 - 文件内容

文档提取器状态：  
📥 输入变量显示：{{onedrive_docs.result}}
🟢 执行成功 - 文档处理完成

Pipeline整体：
✅ 完整数据流正常
✅ 知识库接收到文档内容
```

## 💡 **关键要点**

**令牌过期是OneDrive等OAuth认证服务的正常现象**，解决方法是：

1. 🔄 重新授权（最简单有效）
2. 🔧 检查Azure配置（如果重新授权失败）
3. 🧪 技术调试（高级用户）

**一旦重新授权完成，OneDrive数据源将立即恢复正常工作！**

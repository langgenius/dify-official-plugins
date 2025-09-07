# OneDrive 数据源故障排除指南

## 🚨 常见错误和解决方案

### 1. 404 "Item not found" 错误

**错误信息示例：**
```
ValueError: Microsoft Graph list error: 404 {"error":{"code":"itemNotFound","message":"Item not found"}}
```

**可能原因：**
- ✅ **已修复**: 插件现在会自动回退到根目录
- 尝试访问不存在的文件夹ID
- 用户OneDrive为空
- 权限不足

**解决方案：**

#### 方案1：使用诊断脚本
```bash
cd /Users/frederick/Documents/dify-official-plugins/datasources/onedrive
source venv/bin/activate
python debug_onedrive.py YOUR_ACCESS_TOKEN
```

#### 方案2：检查OneDrive内容
1. 登录 [OneDrive网页版](https://onedrive.live.com)
2. 确认账户中有文件/文件夹
3. 检查是否有权限访问

#### 方案3：重新授权
1. 在Dify中删除OneDrive连接
2. 重新添加并授权
3. 确保授权了所有必需权限

### 2. 401 "Unauthorized" 错误

**解决方案：**
- ✅ **已修复**: 插件现在会自动刷新令牌
- 检查Azure应用注册配置
- 确认权限范围正确

### 3. 点击"下一步"无响应

**排查步骤：**

1. **浏览器开发者工具检查**
   ```javascript
   // 按F12，查看Console标签页
   // 查找红色错误信息
   ```

2. **网络请求检查**
   - Network标签页
   - 查看失败的HTTP请求
   - 检查响应内容

3. **Dify日志检查**
   ```bash
   # Docker用户
   docker-compose logs -f api
   docker-compose logs -f worker
   
   # 直接部署用户
   # 查看API和Worker服务的控制台输出
   ```

## 🔧 Azure应用注册配置

### 必需权限
- `Files.Read` - 读取用户文件
- `Files.Read.All` - 读取所有文件
- `User.Read` - 读取用户基本信息
- `offline_access` - 离线访问

### 重定向URI配置
```
https://your-dify-domain.com/console/api/oauth/callback
```
或本地开发:
```
http://localhost:3000/console/api/oauth/callback
```

## 🧪 测试工具

### 手动API测试
```bash
# 替换YOUR_ACCESS_TOKEN为实际令牌
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
     -H "Accept: application/json" \
     https://graph.microsoft.com/v1.0/me/drive/root/children
```

### Python测试脚本
使用 `debug_onedrive.py` 进行完整诊断

## 📝 常见配置错误

### 1. Client ID/Secret 不匹配
```
解决：重新复制Azure应用注册中的值
```

### 2. 重定向URI不匹配
```
错误：redirect_uri_mismatch
解决：确保Dify配置的回调URL与Azure应用注册一致
```

### 3. 权限不足
```
错误：insufficient_scope
解决：在Azure应用注册中添加必需的API权限
```

## 🔍 调试模式

修改后的插件包含详细的调试输出：
- `DEBUG: Requesting URL: ...` - 显示请求的API端点
- `DEBUG: Prefix: ..., Max keys: ...` - 显示请求参数
- `DEBUG: Token expired, refreshing...` - 令牌刷新状态
- `DEBUG: Item not found for prefix '...', falling back to root` - 404错误处理

## 📞 进一步支持

如果问题持续存在，请提供：
1. 浏览器开发者工具的错误截图
2. Dify后端日志相关部分
3. `debug_onedrive.py` 的完整输出
4. Azure应用注册的权限配置截图

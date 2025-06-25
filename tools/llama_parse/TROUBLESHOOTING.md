# Llama Parse Advanced Tool - Troubleshooting Guide

## Common Issues and Solutions

### 1. Connection Timeout Error

**Error Message:**
```
httpx.ConnectTimeout: The handshake operation timed out
```

**Cause:** The tool cannot access the file URL, usually due to incorrect `FILES_URL` configuration.

**Solution:**

#### For Docker Compose Deployment:
1. Edit your Dify `.env` file
2. Add or update the `FILES_URL` setting:
   ```bash
   FILES_URL=http://api:5001
   ```
3. Restart Dify services:
   ```bash
   docker compose down
   docker compose up -d
   ```

#### For Other Deployment Methods:
1. Edit your Dify `.env` file
2. Add or update the `FILES_URL` setting with your Dify host IP:
   ```bash
   FILES_URL=http://YOUR_DIFY_HOST_IP:5001
   ```
   Example: `FILES_URL=http://192.168.1.101:5001`
3. Restart Dify services

#### Verification Steps:
1. Ensure port 5001 is exposed in your `docker-compose.yaml`
2. Check that the Dify API service is running
3. Verify network connectivity between the plugin and Dify API

### 2. Invalid File URL Error

**Error Message:**
```
ValueError: Invalid file URL 'file:///path/to/file': Request URL is missing an 'http://' or 'https://' protocol
```

**Cause:** The `FILES_URL` environment variable is not set or is incorrect.

**Solution:**
Follow the same steps as above to configure `FILES_URL` correctly.

### 3. HTTP Status Error

**Error Message:**
```
httpx.HTTPStatusError: HTTP error 404 while accessing file 'document.pdf'
```

**Cause:** The file URL is valid but the file doesn't exist or is not accessible.

**Solution:**
1. Check if the file exists in the expected location
2. Verify file permissions
3. Ensure the file service is running correctly

### 4. API Key Issues

**Error Message:**
```
ToolProviderCredentialValidationError: Invalid API key
```

**Cause:** The Llama Cloud API key is invalid or not configured.

**Solution:**
1. Get a valid API key from [Llama Cloud](https://cloud.llamaindex.ai/)
2. Configure the API key in your Dify plugin settings
3. Ensure the API key has the necessary permissions

### 5. File Format Issues

**Error Message:**
```
Unsupported file format
```

**Cause:** The uploaded file format is not supported by LlamaParse.

**Solution:**
Supported formats include:
- PDF (.pdf)
- Microsoft Word (.docx)
- Microsoft PowerPoint (.pptx)
- Text files (.txt)
- And other common document formats

## Advanced Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `FILES_URL` | URL for Dify's file service | `http://api:5001` |
| `LLAMA_CLOUD_API_KEY` | Your Llama Cloud API key | `llama_xxxxxxxxxxxx` |

### Network Configuration

For Docker deployments, ensure your `docker-compose.yaml` includes:

```yaml
services:
  api:
    ports:
      - "5001:5001"
    environment:
      - FILES_URL=http://api:5001
```

### Plugin Configuration

In your Dify plugin settings, ensure:
1. The Llama Cloud API key is correctly configured
2. The plugin has access to the file service
3. Network connectivity is established

## Performance Optimization

### Timeout Settings
- Default timeout: 30 seconds
- Adjust based on your network conditions
- Large files may require longer timeouts

### Memory Usage
- LLM mode uses more memory than standard parsing
- Monitor memory usage for large documents
- Consider using `max_pages` for very large documents

### Cost Optimization
- Use `target_pages` to parse only needed pages
- Set `max_pages` to limit processing
- Monitor API usage in Llama Cloud dashboard

## Debugging Tips

### Enable Verbose Mode
Set `verbose: true` in the tool parameters to get detailed logging information.

### Check Logs
Monitor the plugin logs for detailed error information:
```bash
docker compose logs -f api
```

### Test File Access
Test file access manually:
```bash
curl -I http://api:5001/files/test.pdf
```

### Network Connectivity
Test network connectivity:
```bash
ping api  # For Docker Compose
ping YOUR_DIFY_HOST_IP  # For other deployments
```

## Getting Help

If you continue to experience issues:

1. Check the [Dify documentation](https://docs.dify.ai/)
2. Review the [Llama Cloud documentation](https://docs.llamaindex.ai/)
3. Check the plugin logs for detailed error messages
4. Verify all configuration settings are correct

## Common Configuration Examples

### Docker Compose (.env)
```bash
FILES_URL=http://api:5001
LLAMA_CLOUD_API_KEY=llama_xxxxxxxxxxxx
```

### Standalone Deployment (.env)
```bash
FILES_URL=http://192.168.1.101:5001
LLAMA_CLOUD_API_KEY=llama_xxxxxxxxxxxx
```

### Plugin Settings
```yaml
credentials:
  llama_cloud_api_key: "llama_xxxxxxxxxxxx"
``` 
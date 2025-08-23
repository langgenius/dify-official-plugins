# Gemini Document Filtering Tests

This directory contains comprehensive tests for the Gemini API document filtering functionality.

## Test Structure

### `test_document_filtering.py`
- **Unit Tests** (`TestDocumentFilteringUnit`): No API key required
- **Integration Tests** (`TestDocumentFilteringIntegration`): Requires valid API key

## Test Configuration

### Environment Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Set your Gemini API key in `.env`:
   ```bash
   GEMINI_API_KEY=your_actual_api_key_here
   ```

3. Get your API key from [Google AI Studio](https://aistudio.google.com/apikey)

### Test Configuration

The tests use minimal cost configuration:
- **Model**: `gemini-2.5-flash-lite`
- **Max Output Tokens**: 5 (to minimize costs)
- **Temperature**: 0.1

You can modify these settings in the `GEMINI_TEST_CONFIG` dictionary in the test file.

## Running Tests

### All Tests
```bash
# Run all tests
uv run pytest

# Run with detailed output
uv run pytest models/tests/test_document_filtering.py -v -s
```

### Unit Tests Only (No API Key Required)
```bash
uv run pytest models/tests/test_document_filtering.py::TestDocumentFilteringUnit -v
```

### Integration Tests Only (API Key Required)
```bash
uv run pytest models/tests/test_document_filtering.py::TestDocumentFilteringIntegration -v -m integration
```

### Skip Integration Tests
```bash
uv run pytest models/tests/test_document_filtering.py -v -m "not integration"
```

## Test Features

### Unit Tests Cover:
- ✅ Supported document types (PDF, TXT, HTML, Markdown)
- ✅ Unsupported document types (DOCX, XLSX, PPT, etc.)
- ✅ MIME type filtering
- ✅ File extension filtering
- ✅ Case-insensitive extension filtering
- ✅ Mixed supported/unsupported content
- ✅ Empty content after filtering
- ✅ File caching mechanism
- ✅ Error handling

### Integration Tests Cover:
- ✅ Real PDF upload and processing
- ✅ Real text document upload
- ✅ Real Markdown document upload
- ✅ Real filtering with mixed documents
- ✅ Real unsupported document rejection

## Memory Management

- Tests use `MemoryFileCache` instead of persistent file cache
- No files are written to disk during testing
- Cache is cleared after each test

## Test Data

The `DocumentGenerator` class creates minimal valid documents:
- **PDF**: Minimal valid PDF structure
- **Text**: Plain text content
- **HTML**: Basic HTML structure
- **Markdown**: Simple Markdown content
- **DOCX**: Minimal ZIP structure (for negative testing)

## Cost Optimization

Integration tests are designed to minimize API costs:
- Very short responses (5 tokens max)
- Simple test documents
- Efficient test cases

## Extensibility

The test architecture supports easy extension for:
- Additional document types
- Image/video/audio testing (framework ready)
- Different Gemini models
- Custom test configurations

## Troubleshooting

### Common Issues

1. **"GEMINI_API_KEY not found"**
   - Set up your `.env` file with valid API key

2. **"Invalid GEMINI_API_KEY"**
   - Verify your API key at Google AI Studio
   - Check API key permissions

3. **Integration tests skipped**
   - This is normal behavior when no API key is provided
   - Only unit tests will run

### Debug Mode
```bash
# Run with debug logging
uv run pytest models/tests/test_document_filtering.py -v -s --log-cli-level=DEBUG
```
# Vertex AI Plugin - GenAI SDK Migration

## Overview
This migration addresses the deprecation of Google's Vertex AI SDK (`google-cloud-aiplatform`) by migrating to the new Google Gen AI SDK (`google-genai`). The deprecated modules will be removed after **June 24, 2026**.

## Changes Made

### 1. Dependencies (`requirements.txt`)
- **Removed**: `google-cloud-aiplatform==1.97.0`
- **Kept**: `google-genai==1.11.0` (already present)
- **Added**: `google-api-core==2.23.0` (for exception types used in error mapping)
- **Added**: `tiktoken==0.8.0` (for token counting fallback)

### 2. LLM Implementation (`models/llm/llm.py`)

#### Import Changes
- **Removed**: `import vertexai.generative_models as glm`
- **Removed**: `from google.cloud import aiplatform`
- **Updated**: Imports now use `from google import genai` and `from google.genai import types`

#### Key Method Updates

##### `_generate()` - Core Generation Method
- Replaced `aiplatform.init()` with `genai.Client()` initialization
- Updated client to use Vertex AI mode: `genai.Client(vertexai=True, ...)`
- Changed content format from `glm.Content` objects to dict format
- Updated config to use `types.GenerateContentConfig`
- Replaced `generate_content()` calls with new SDK methods

##### `_format_message_to_genai_content()` (formerly `_format_message_to_glm_content`)
- Converted from returning `glm.Content` objects to returning dict structures
- Updated part formats:
  - Text: `{"text": content}`
  - Inline data: `{"inline_data": {"mime_type": ..., "data": ...}}`
  - Function calls: `{"function_call": {...}}`

##### `_convert_tools_to_genai_tool()` (formerly `_convert_tools_to_glm_tool`)
- Updated to return `list[types.Tool]` instead of `list[glm.Tool]`
- Changed property schema format from `type_` to `type`
- Function declarations now use dict format

##### `_convert_grounding_to_genai_tool()` (formerly `_convert_grounding_to_glm_tool`)
- Simplified to use `types.Tool(google_search=types.GoogleSearch())`
- Removed complex `GoogleSearchRetrieval` configuration (handled internally by SDK)

##### `_handle_generate_response()`
- Updated type hint: `types.GenerateContentResponse` instead of `glm.GenerationResponse`
- Added defensive checks for response structure
- Updated attribute access patterns for new SDK

##### `_handle_generate_stream_response()`
- Updated type hint for response parameter
- Enhanced error handling for streaming responses
- Updated attribute access for grounding metadata

### 3. Text Embedding Implementation (`models/text_embedding/text_embedding.py`)

#### Import Changes
- **Removed**: `from google.cloud import aiplatform`
- **Removed**: `from vertexai.language_models import TextEmbeddingModel as VertexTextEmbeddingModel`
- **Added**: `from google import genai` and `from google.genai import types`

#### Key Method Updates

##### `_invoke()`
- Replaced `aiplatform.init()` with `genai.Client()` initialization
- Updated to use Vertex AI mode: `genai.Client(vertexai=True, ...)`
- Updated call to `_embedding_invoke()` with new parameters

##### `_embedding_invoke()`
- Replaced `VertexTextEmbeddingModel.from_pretrained()` with GenAI client
- Changed from `client.get_embeddings()` to `client.models.embed_content()`
- Added task type mapping for input types (RETRIEVAL_DOCUMENT, RETRIEVAL_QUERY)
- Implemented token counting with fallback to tiktoken estimation
- Updated return type annotation to proper tuple format

##### `validate_credentials()`
- Replaced `aiplatform.init()` with `genai.Client()` initialization
- Updated validation call to use new `_embedding_invoke()` signature

### 4. Unchanged Components

#### Claude/Anthropic Models
- No changes made to Claude model implementation
- Still uses `anthropic` package which is not affected by the deprecation
- Methods: `_generate_anthropic()`, `_handle_claude_response()`, etc.

#### Provider Validation
- `provider/vertex_ai.py` - No changes needed
- Validation still uses the same public interface

## Compatibility

### Maintained Interfaces
✅ All Dify plugin interfaces remain unchanged:
- `_invoke()` method signature
- `get_num_tokens()` method signature
- `validate_credentials()` method signature
- All return types (LLMResult, LLMResultChunk, TextEmbeddingResult, etc.)
- Error handling patterns

### Breaking Changes
❌ None for Dify users - this is a purely internal migration

### New Features
✅ Now supports latest Gemini models (2.5, 2.0, etc.)
✅ Better compatibility with Google's current API
✅ Prepares for future GenAI SDK enhancements

## Testing Recommendations

1. **Gemini Models**: Test generation with various Gemini models (1.5, 2.0, 2.5)
2. **Streaming**: Verify streaming responses work correctly
3. **Function Calling**: Test tool/function calling capabilities
4. **Grounding**: Test Google Search grounding feature
5. **Embeddings**: Test text embedding generation
6. **Claude Models**: Verify Claude models still work (should be unaffected)
7. **Error Handling**: Test various error scenarios

## Migration Timeline

- **Current**: Using deprecated `google-cloud-aiplatform` SDK
- **After this PR**: Using new `google-genai` SDK
- **June 24, 2026**: Deprecated SDK modules will be removed by Google

## References

- [Google GenAI SDK Migration Guide](https://cloud.google.com/vertex-ai/generative-ai/docs/deprecations/genai-vertexai-sdk)
- [GitHub Issue #1476](https://github.com/langgenius/dify-official-plugins/issues/1476)

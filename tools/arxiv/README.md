# ArXiv Search Plugin

A powerful Dify plugin for searching and retrieving scientific papers from the ArXiv repository. This plugin enables seamless integration of academic research capabilities into your AI applications.

## 🔬 What is ArXiv?

ArXiv is a free distribution service and open-access archive for scholarly articles in physics, mathematics, computer science, quantitative biology, quantitative finance, statistics, electrical engineering, systems science, and economics. Founded in 1991, it hosts over 2 million research papers and is widely used by researchers worldwide.

## ✨ Features

- **Comprehensive Search**: Search by keywords, author names, or ArXiv IDs
- **Rich Metadata**: Returns publication dates, titles, authors, and abstracts
- **Configurable Results**: Customize the number of results and content length
- **Error Handling**: Robust error handling for API failures and edge cases
- **AI-Powered Summaries**: Automatic summarization of search results using Dify's model capabilities

## 🚀 Quick Start

### Installation

1. **From Plugin Marketplace** (Recommended)
   - Navigate to the Dify Plugin Marketplace
   - Search for "ArXiv"
   - Click "Install" to add it to your workspace

2. **Manual Installation**
   ```bash
   # Clone the repository
   git clone <your-repo-url>
   cd arxiv-plugin
   
   # Install dependencies
   pip install -r requirements.txt
   ```

### Basic Usage

Once installed, you can use the ArXiv plugin in three ways:

#### 1. Agent Applications
Add the ArXiv tool to your Agent and interact naturally:

```
User: "Find recent papers about transformer models in NLP"
Agent: *Uses ArXiv tool to search and summarize results*
```

#### 2. Chatflow Applications
Add an ArXiv tool node to your chatflow for automated research workflows.

#### 3. Workflow Applications
Integrate ArXiv searches into complex automation pipelines.

## 📖 Usage Examples

### Search by Keywords
```
Query: "quantum computing machine learning"
```

### Search by Author
```
Query: "Geoffrey Hinton"
```

### Search by ArXiv ID
```
Query: "2103.00020"
```

### Advanced Search Queries
```
Query: "ti:transformer AND cat:cs.CL"  # Title contains "transformer" in Computer Science - Computation and Language
Query: "au:Vaswani AND ti:attention"   # Author Vaswani with "attention" in title
```

## ⚙️ Configuration

### Plugin Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Search query (keywords, author, or ArXiv ID) |

### Advanced Configuration (Code Level)

The `ArxivAPIWrapper` class supports additional configuration:

```python
arxiv = ArxivAPIWrapper(
    top_k_results=3,                    # Number of results to return
    ARXIV_MAX_QUERY_LENGTH=300,         # Maximum query length
    load_max_docs=100,                  # Maximum documents to load
    load_all_available_meta=False,      # Include all metadata
    doc_content_chars_max=4000          # Maximum content length
)
```

## 🛠️ Development

### Project Structure
```
arxiv-plugin/
├── main.py                 # Plugin entry point
├── manifest.yml           # Plugin configuration
├── requirements.txt       # Python dependencies
├── tools/
│   ├── arxiv_search.py    # Main tool implementation
│   └── arxiv_search.yaml  # Tool configuration
└── provider/
    └── arxiv.yaml         # Provider configuration
```

### Key Components

#### 1. ArxivAPIWrapper (`tools/arxiv_search.py`)
The core wrapper around the ArXiv API with features:
- Query validation and truncation
- Error handling for network issues
- Result formatting and content limiting
- Metadata extraction

#### 2. ArxivSearchTool
Dify tool implementation that:
- Validates input parameters
- Invokes the ArXiv API wrapper
- Generates AI-powered summaries of results
- Returns formatted responses

### Adding Custom Features

To extend the plugin functionality:

1. **Modify Search Parameters**
   ```python
   # In ArxivAPIWrapper.__init__
   self.top_k_results = 5  # Increase result count
   ```

2. **Add Custom Filtering**
   ```python
   # In ArxivAPIWrapper.run()
   filtered_results = [r for r in results if some_condition(r)]
   ```

3. **Enhance Output Format**
   ```python
   # Modify the docs list comprehension
   docs = [
       f"📅 Published: {result.updated.date()}\n"
       f"📄 Title: {result.title}\n"
       f"👥 Authors: {', '.join(a.name for a in result.authors)}\n"
       f"🔗 URL: {result.entry_id}\n"
       f"📝 Summary: {result.summary}"
       for result in results
   ]
   ```

## 🔧 API Reference

### ArxivAPIWrapper Methods

#### `run(query: str) -> str`
Performs an ArXiv search and returns formatted results.

**Parameters:**
- `query`: Search query string (max 300 characters)

**Returns:**
- Formatted string with paper details or error message

**Example:**
```python
wrapper = ArxivAPIWrapper()
results = wrapper.run("machine learning transformers")
```

### Error Handling

The plugin handles several error scenarios:

| Error Type | Description | Response |
|------------|-------------|----------|
| `ArxivError` | General ArXiv API error | "Arxiv exception: {error}" |
| `UnexpectedEmptyPageError` | Empty response from API | "Arxiv exception: {error}" |
| `HTTPError` | Network/HTTP issues | "Arxiv exception: {error}" |
| No results | Query returns no papers | "No good Arxiv Result was found" |
| Empty query | Missing search query | "Please input query" |

## 🧪 Testing

### Manual Testing
1. Install the plugin in your Dify workspace
2. Create a simple Agent application
3. Add the ArXiv tool
4. Test with various query types:
   - Keywords: "neural networks"
   - Author: "Yann LeCun"
   - ArXiv ID: "1706.03762"

### Unit Testing
```python
# Example test case
def test_arxiv_search():
    wrapper = ArxivAPIWrapper(top_k_results=1)
    result = wrapper.run("attention is all you need")
    assert "Title:" in result
    assert "Authors:" in result
```

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. **Fork the Repository**
2. **Create a Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make Your Changes**
4. **Test Thoroughly**
5. **Submit a Pull Request**

### Contribution Guidelines
- Follow Python PEP 8 style guidelines
- Add docstrings to new functions
- Include tests for new features
- Update documentation as needed

## 📚 Resources

### ArXiv Resources
- [ArXiv.org](https://arxiv.org/) - Official ArXiv website
- [ArXiv API Documentation](https://arxiv.org/help/api/index)
- [ArXiv Python Library](https://lukasschwab.me/arxiv.py/) - Official Python wrapper

### Dify Resources
- [Dify Documentation](https://docs.dify.ai/)
- [Plugin Development Guide](https://docs.dify.ai/plugins)
- [Dify Community](https://github.com/langgenius/dify)

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🐛 Troubleshooting

### Common Issues

**Issue**: "No good Arxiv Result was found"
- **Solution**: Try different keywords, check spelling, or broaden your search terms

**Issue**: "Arxiv exception: HTTPError"
- **Solution**: Check internet connection or try again later (ArXiv may be temporarily unavailable)

**Issue**: Results are truncated
- **Solution**: Increase `doc_content_chars_max` in the configuration

**Issue**: Tool not appearing in Dify
- **Solution**: Ensure plugin is properly installed and workspace is refreshed

### Debug Mode

Enable debug logging for detailed error information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📊 Performance Notes

- **Rate Limits**: ArXiv has rate limiting; avoid excessive concurrent requests
- **Response Time**: Searches typically take 1-3 seconds depending on query complexity
- **Memory Usage**: Plugin uses minimal memory (~1MB as configured)
- **Content Limits**: Results are truncated to prevent memory issues with large papers

## 🔄 Version History

- **v0.0.2**: Current version with enhanced error handling and AI summaries
- **v0.0.1**: Initial release with basic search capabilities
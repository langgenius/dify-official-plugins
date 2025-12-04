import re
import json
from typing import List, Dict, Any, Optional


class MarkdownToADF:
    """Markdown to Atlassian Document Format converter.

    Responsibilities:
    - Tokenize block-level markdown (headings, lists, paragraphs).
    - Tokenize inline markdown (bold, italic, links, inline code).
    - Build Atlassian Document Format (ADF) node structure.
    """
    
    def __init__(self):
        self.rules = [
            {'type': 'heading', 'regex': re.compile(r'^(#{1,6})\s+(.*)$')},
            {'type': 'listItem', 'regex': re.compile(r'^(\s*)([-*+]|\d+\.)\s+(.*)$')},
        ]
    
    def build_token(self, token_type: str, match: re.Match, original_line: str) -> Dict[str, Any]:
        """Build token based on type and regex match."""
        if token_type == 'heading':
            return {
                'type': token_type,
                'depth': len(match.group(1)),
                'value': match.group(2).strip()
            }
        elif token_type == 'listItem':
            return {
                'type': token_type,
                'indent': len(match.group(1)),
                'marker': match.group(2),
                'value': match.group(3)
            }
        else:  # text
            return {
                'type': token_type,
                'value': original_line
            }
    
    def tokenize_inline_elements(self, text: str) -> List[Dict[str, Any]]:
        """Tokenize inline markdown elements."""
        tokens = []
        index = 0
        
        while index < len(text):
            matched = False
            
            # Check for bold
            bold_match = re.match(r'^\*\*([^*]+)\*\*', text[index:])
            if bold_match:
                tokens.append({'type': 'bold', 'value': bold_match.group(1)})
                index += len(bold_match.group(0))
                matched = True
                continue
            
            # Check for italic
            italic_match = re.match(r'^\*([^*]+)\*', text[index:])
            if italic_match:
                tokens.append({'type': 'italic', 'value': italic_match.group(1)})
                index += len(italic_match.group(0))
                matched = True
                continue
            
            # Check for links
            link_match = re.match(r'^\[([^\]]+)\]\(([^)]+)\)', text[index:])
            if link_match:
                tokens.append({
                    'type': 'link',
                    'text': link_match.group(1),
                    'href': link_match.group(2)
                })
                index += len(link_match.group(0))
                matched = True
                continue
            
            # Check for inline code
            code_match = re.match(r'^`([^`]+)`', text[index:])
            if code_match:
                tokens.append({'type': 'inlineCode', 'value': code_match.group(1)})
                index += len(code_match.group(0))
                matched = True
                continue
            
            # Regular text
            if not matched:
                text_end = index + 1
                # Get text until next markup
                while text_end < len(text):
                    remaining = text[text_end:]
                    if re.match(r'^(\*\*|\*|\[|`)', remaining):
                        break
                    text_end += 1
                
                if text_end > index:
                    text_content = text[index:text_end]
                    if text_content.strip():
                        tokens.append({'type': 'text', 'value': text_content})
                    index = text_end
                else:
                    # Single character case
                    tokens.append({'type': 'text', 'value': text[index]})
                    index += 1
        
        return tokens
    
    def group_paragraphs(self, tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group consecutive text tokens into paragraphs."""
        result = []
        current_paragraph = []
        
        for token in tokens:
            if token['type'] == 'text':
                current_paragraph.append(token['value'])
            elif token['type'] == 'empty':
                # Empty line ends current paragraph
                if current_paragraph:
                    paragraph_text = ' '.join(current_paragraph)
                    inline_tokens = self.tokenize_inline_elements(paragraph_text)
                    result.append({
                        'type': 'paragraph',
                        'children': inline_tokens
                    })
                    current_paragraph = []
            else:
                # Heading or list item ends current paragraph
                if current_paragraph:
                    paragraph_text = ' '.join(current_paragraph)
                    inline_tokens = self.tokenize_inline_elements(paragraph_text)
                    result.append({
                        'type': 'paragraph',
                        'children': inline_tokens
                    })
                    current_paragraph = []
                result.append(token)
        
        # Add final paragraph
        if current_paragraph:
            paragraph_text = ' '.join(current_paragraph)
            inline_tokens = self.tokenize_inline_elements(paragraph_text)
            result.append({
                'type': 'paragraph',
                'children': inline_tokens
            })
        
        return result
    
    def tokenize(self, source: str) -> List[Dict[str, Any]]:
        """Tokenize markdown source."""
        lines = source.split('\n')
        tokens = []
        
        for line in lines:
            if line.strip() == '':
                tokens.append({'type': 'empty', 'value': ''})
                continue
            
            matched = False
            for rule in self.rules:
                match = rule['regex'].match(line)
                if match:
                    matched = True
                    tokens.append(self.build_token(rule['type'], match, line))
                    break
            
            if not matched:
                tokens.append({'type': 'text', 'value': line})
        
        return self.group_paragraphs(tokens)
    
    def adjust_list_stack(self, list_stack: List[Dict], content: List, target_indent: int, marker: str):
        """Adjust list stack for proper nesting."""
        # Close lists deeper than target indent
        while list_stack and list_stack[-1]['indent'] > target_indent:
            finished_list = list_stack.pop()
            if not list_stack:
                content.append(finished_list['list'])
            else:
                # Add as nested list to parent list item
                parent_list_info = list_stack[-1]
                last_item = parent_list_info['list']['content'][-1]
                last_item['content'].append(finished_list['list'])
        
        # Create new list if no list exists at this level
        if not list_stack or list_stack[-1]['indent'] != target_indent:
            is_ordered = bool(re.match(r'\d+\.', marker))
            new_list = {
                'type': 'orderedList' if is_ordered else 'bulletList',
                'content': []
            }
            list_stack.append({
                'list': new_list,
                'indent': target_indent
            })
    
    def close_all_lists(self, list_stack: List[Dict], content: List):
        """Close all remaining lists."""
        while list_stack:
            finished_list = list_stack.pop()
            if not list_stack:
                content.append(finished_list['list'])
            else:
                # Add as nested list to parent list item
                parent_list_info = list_stack[-1]
                last_item = parent_list_info['list']['content'][-1]
                last_item['content'].append(finished_list['list'])
    
    def inline_to_adf(self, inline_tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert inline tokens to ADF format."""
        result = []
        
        for token in inline_tokens:
            if token['type'] == 'text':
                result.append({
                    'type': 'text',
                    'text': token['value']
                })
            elif token['type'] == 'bold':
                result.append({
                    'type': 'text',
                    'text': token['value'],
                    'marks': [{'type': 'strong'}]
                })
            elif token['type'] == 'italic':
                result.append({
                    'type': 'text',
                    'text': token['value'],
                    'marks': [{'type': 'em'}]
                })
            elif token['type'] == 'link':
                result.append({
                    'type': 'text',
                    'text': token['text'],
                    'marks': [{
                        'type': 'link',
                        'attrs': {
                            'href': token['href']
                        }
                    }]
                })
            elif token['type'] == 'inlineCode':
                result.append({
                    'type': 'text',
                    'text': token['value'],
                    'marks': [{'type': 'code'}]
                })
        
        return result
    
    def to_adf(self, tokens: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert tokens to ADF format."""
        content = []
        list_stack = []
        
        for token in tokens:
            if token['type'] == 'heading':
                # Close any ongoing lists
                self.close_all_lists(list_stack, content)
                
                content.append({
                    'type': 'heading',
                    'attrs': {
                        'level': token['depth']
                    },
                    'content': self.inline_to_adf([{'type': 'text', 'value': token['value']}])
                })
            
            elif token['type'] == 'paragraph':
                # Close any ongoing lists
                self.close_all_lists(list_stack, content)
                
                content.append({
                    'type': 'paragraph',
                    'content': self.inline_to_adf(token['children'])
                })
            
            elif token['type'] == 'listItem':
                # Adjust list stack for proper nesting
                self.adjust_list_stack(list_stack, content, token['indent'], token['marker'])
                
                # Process list item inline elements
                inline_tokens = self.tokenize_inline_elements(token['value'])
                
                current_list_info = list_stack[-1]
                current_list_info['list']['content'].append({
                    'type': 'listItem',
                    'content': [{
                        'type': 'paragraph',
                        'content': self.inline_to_adf(inline_tokens)
                    }]
                })
        
        # Close any remaining lists
        self.close_all_lists(list_stack, content)
        
        return {
            'version': 1,
            'type': 'doc',
            'content': content
        }
    
    def markdown_to_adf(self, source: str) -> Dict[str, Any]:
        """Convert markdown source to ADF format."""
        tokens = self.tokenize(source)
        return self.to_adf(tokens)

# For backward compatibility and testing
def markdown_to_adf(source: str) -> Dict[str, Any]:
    """Convenience function for converting markdown to ADF."""
    converter = MarkdownToADF()
    return converter.markdown_to_adf(source)


if __name__ == '__main__':
    # Example usage
    test_markdown = """# Heading 1
    
This is a **bold** text and *italic* text with [link](https://example.com) and `inline code`.

## Heading 2

- List item 1
- List item 2
  - Nested item 1
  - Nested item 2

1. Ordered item 1
2. Ordered item 2
"""
    
    result = markdown_to_adf(test_markdown)
    print(json.dumps(result, indent=2, ensure_ascii=False))
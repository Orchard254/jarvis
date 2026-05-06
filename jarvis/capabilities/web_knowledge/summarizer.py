"""
Summarizer Capability
Compress long text using AI models
"""

from typing import Dict, Any, Optional
from ..base import Capability


class Summarizer(Capability):
    """Text summarization capability using AI models"""
    
    def __init__(self, model_name: str = "gpt-oss-120b", max_length: int = 500):
        """
        Initialize summarizer
        
        Args:
            model_name: AI model to use for summarization
            max_length: Maximum length of summary in words
        """
        self.model_name = model_name
        self.max_length = max_length
        # Note: In production, this would initialize connection to GPT-OSS 120B
    
    def execute(self, text: str, summary_type: str = "brief", 
                length_ratio: float = 0.2, **kwargs) -> Dict[str, Any]:
        """
        Summarize text content
        
        Args:
            text: Input text to summarize
            summary_type: Type of summary (brief, detailed, bullet_points, executive)
            length_ratio: Target length as ratio of original (0.1-0.5)
            
        Returns:
            Dictionary with success status and summary
        """
        try:
            if not text or not text.strip():
                return {"success": False, "error": "Input text cannot be empty"}
            
            # Validate length ratio
            length_ratio = max(0.05, min(0.5, length_ratio))
            
            # Pre-process text
            cleaned_text = self._clean_text(text)
            
            if len(cleaned_text.split()) < 50:
                # Text too short to summarize meaningfully
                return {
                    "success": True,
                    "output": {
                        "original_length": len(cleaned_text),
                        "summary": cleaned_text,
                        "note": "Text too short for summarization, returning original"
                    }
                }
            
            # Generate summary based on type
            if summary_type == "brief":
                summary = self._generate_brief_summary(cleaned_text, length_ratio)
            elif summary_type == "detailed":
                summary = self._generate_detailed_summary(cleaned_text, length_ratio)
            elif summary_type == "bullet_points":
                summary = self._generate_bullet_summary(cleaned_text)
            elif summary_type == "executive":
                summary = self._generate_executive_summary(cleaned_text)
            else:
                summary = self._generate_brief_summary(cleaned_text, length_ratio)
            
            return {
                "success": True,
                "output": {
                    "original_length": len(text),
                    "summary_length": len(summary),
                    "summary_type": summary_type,
                    "compression_ratio": round(len(summary) / len(text) * 100, 2) if text else 0,
                    "summary": summary
                }
            }
        except Exception as e:
            return {"success": False, "error": f"Summarization failed: {str(e)}"}
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize input text"""
        # Remove excessive whitespace
        import re
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()
    
    def _generate_brief_summary(self, text: str, ratio: float) -> str:
        """Generate a brief summary"""
        # Placeholder: In production, call GPT-OSS 120B
        # For now, use extractive summarization (first sentences)
        sentences = text.replace('\n', ' ').split('. ')
        target_sentences = max(3, int(len(sentences) * ratio))
        
        summary = '. '.join(sentences[:target_sentences])
        if not summary.endswith('.'):
            summary += '.'
        
        return summary
    
    def _generate_detailed_summary(self, text: str, ratio: float) -> str:
        """Generate a detailed summary"""
        # Placeholder: In production, call GPT-OSS 120B with detailed prompt
        paragraphs = text.split('\n\n')
        target_paragraphs = max(2, int(len(paragraphs) * ratio))
        
        summary_parts = []
        for para in paragraphs[:target_paragraphs]:
            sentences = para.split('. ')
            if len(sentences) > 2:
                summary_parts.append('. '.join(sentences[:3]) + '.')
            else:
                summary_parts.append(para)
        
        return '\n\n'.join(summary_parts)
    
    def _generate_bullet_summary(self, text: str) -> str:
        """Generate bullet point summary"""
        # Placeholder: In production, call GPT-OSS 120B
        sentences = text.replace('\n', ' ').split('. ')
        # Extract key sentences (simplified heuristic)
        key_sentences = [s.strip() for s in sentences if len(s.split()) > 5][:5]
        
        bullets = [f"• {s}" for s in key_sentences if s and not s.endswith('?')]
        return '\n'.join(bullets)
    
    def _generate_executive_summary(self, text: str) -> str:
        """Generate executive summary"""
        # Placeholder: In production, call GPT-OSS 120B with executive summary prompt
        # Extract first paragraph and last conclusion
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        if len(paragraphs) >= 2:
            summary = paragraphs[0] + '\n\n' + paragraphs[-1]
        elif len(paragraphs) == 1:
            summary = paragraphs[0]
        else:
            summary = text[:500]
        
        return summary


# Factory function
def create_capability(**kwargs) -> Capability:
    return Summarizer(**kwargs)

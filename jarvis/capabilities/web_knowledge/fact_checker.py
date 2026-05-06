"""
Fact Checker Capability
Validate claims across multiple sources
"""

import requests
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from ..base import Capability


class FactChecker(Capability):
    """Cross-source fact validation capability"""
    
    def __init__(self, timeout: int = 10):
        """
        Initialize fact checker
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (JARVIS Agent)'
        })
    
    def execute(self, claim: str, sources: Optional[List[str]] = None, 
                strict_mode: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Validate a claim against multiple sources
        
        Args:
            claim: The claim/statement to verify
            sources: Optional list of trusted sources to check
            strict_mode: If True, require consensus across all sources
            
        Returns:
            Dictionary with verification results and confidence score
        """
        try:
            if not claim or not claim.strip():
                return {"success": False, "error": "Claim cannot be empty"}
            
            # Default trusted sources for fact-checking
            if not sources:
                sources = [
                    "https://www.snopes.com",
                    "https://www.factcheck.org",
                    "https://www.politifact.com",
                    "https://reuters.com",
                    "https://apnews.com"
                ]
            
            # Search for the claim across sources
            verification_results = self._verify_claim(claim, sources)
            
            # Analyze consensus
            analysis = self._analyze_consensus(verification_results, strict_mode)
            
            return {
                "success": True,
                "output": {
                    "claim": claim,
                    "verification_status": analysis["status"],
                    "confidence_score": analysis["confidence"],
                    "sources_checked": len(verification_results),
                    "supporting_sources": analysis["supporting"],
                    "contradicting_sources": analysis["contradicting"],
                    "neutral_sources": analysis["neutral"],
                    "evidence": verification_results,
                    "recommendation": analysis["recommendation"]
                }
            }
        except Exception as e:
            return {"success": False, "error": f"Fact checking failed: {str(e)}"}
    
    def _verify_claim(self, claim: str, sources: List[str]) -> List[Dict]:
        """Search for claim verification across sources"""
        results = []
        
        # Extract key terms from claim for searching
        key_terms = self._extract_key_terms(claim)
        
        for source_url in sources[:5]:  # Limit to 5 sources
            try:
                # Search within the source site
                search_query = f"site:{source_url.split('/')[2]} {key_terms}"
                search_results = self._search_web(search_query, num_results=3)
                
                if search_results:
                    for result in search_results:
                        # Fetch and analyze the page
                        relevance_score = self._calculate_relevance(claim, result.get('snippet', ''))
                        
                        if relevance_score > 0.3:  # Only include relevant results
                            results.append({
                                "source": source_url,
                                "url": result.get('url', ''),
                                "title": result.get('title', ''),
                                "snippet": result.get('snippet', ''),
                                "relevance_score": relevance_score,
                                "verdict": self._infer_verdict(result.get('snippet', ''), claim)
                            })
            except Exception:
                continue
        
        return results
    
    def _search_web(self, query: str, num_results: int = 3) -> List[Dict]:
        """Perform web search (using DuckDuckGo)"""
        try:
            response = self.session.get(
                "https://html.duckduckgo.com/html/",
                params={'q': query},
                timeout=self.timeout
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            for result in soup.select('.result')[:num_results]:
                title_tag = result.select_one('.result__a')
                snippet_tag = result.select_one('.result__snippet')
                
                if title_tag and snippet_tag:
                    results.append({
                        "title": title_tag.get_text(strip=True),
                        "url": title_tag.get('href', ''),
                        "snippet": snippet_tag.get_text(strip=True)
                    })
            
            return results
        except Exception:
            return []
    
    def _extract_key_terms(self, claim: str) -> str:
        """Extract key search terms from claim"""
        # Remove common words and extract nouns/proper nouns
        stop_words = {'the', 'is', 'are', 'was', 'were', 'that', 'this', 'which', 'who', 'what'}
        words = claim.lower().split()
        key_words = [w for w in words if w not in stop_words and len(w) > 3]
        return ' '.join(key_words[:5])  # Top 5 key terms
    
    def _calculate_relevance(self, claim: str, text: str) -> float:
        """Calculate relevance score between claim and text"""
        claim_words = set(claim.lower().split())
        text_words = set(text.lower().split())
        
        if not text_words:
            return 0.0
        
        overlap = claim_words.intersection(text_words)
        return len(overlap) / len(claim_words)
    
    def _infer_verdict(self, snippet: str, claim: str) -> str:
        """Infer verdict from snippet content"""
        snippet_lower = snippet.lower()
        
        # Keywords indicating truth value
        true_keywords = ['true', 'correct', 'accurate', 'confirmed', 'verified']
        false_keywords = ['false', 'fake', 'debunked', 'incorrect', 'misleading', 'hoax']
        mixed_keywords = ['partially', 'mixed', 'unproven', 'unclear', 'disputed']
        
        true_count = sum(1 for kw in true_keywords if kw in snippet_lower)
        false_count = sum(1 for kw in false_keywords if kw in snippet_lower)
        mixed_count = sum(1 for kw in mixed_keywords if kw in mixed_keywords if kw in snippet_lower)
        
        if false_count > true_count and false_count > mixed_count:
            return "FALSE"
        elif true_count > false_count and true_count > mixed_count:
            return "TRUE"
        elif mixed_count > 0:
            return "MIXED/UNPROVEN"
        else:
            return "NEUTRAL"
    
    def _analyze_consensus(self, results: List[Dict], strict_mode: bool) -> Dict:
        """Analyze consensus across sources"""
        if not results:
            return {
                "status": "UNVERIFIED",
                "confidence": 0.0,
                "supporting": [],
                "contradicting": [],
                "neutral": [],
                "recommendation": "Insufficient sources to verify claim"
            }
        
        # Categorize sources
        supporting = [r for r in results if r.get('verdict') == 'TRUE']
        contradicting = [r for r in results if r.get('verdict') == 'FALSE']
        neutral = [r for r in results if r.get('verdict') in ['NEUTRAL', 'MIXED/UNPROVEN']]
        
        # Calculate confidence
        total = len(results)
        if strict_mode:
            # Require unanimous agreement
            if len(supporting) == total:
                status = "VERIFIED_TRUE"
                confidence = 1.0
            elif len(contradicting) == total:
                status = "VERIFIED_FALSE"
                confidence = 1.0
            else:
                status = "DISPUTED"
                confidence = 0.5
        else:
            # Majority rules
            if len(supporting) > len(contradicting):
                status = "LIKELY_TRUE"
                confidence = len(supporting) / total
            elif len(contradicting) > len(supporting):
                status = "LIKELY_FALSE"
                confidence = len(contradicting) / total
            else:
                status = "INCONCLUSIVE"
                confidence = 0.5
        
        # Generate recommendation
        if confidence >= 0.8:
            recommendation = f"High confidence: Claim appears to be {status.replace('_', ' ').lower()}"
        elif confidence >= 0.6:
            recommendation = f"Moderate confidence: Further verification recommended"
        else:
            recommendation = "Low confidence: Claim could not be reliably verified"
        
        return {
            "status": status,
            "confidence": round(confidence, 2),
            "supporting": [r['source'] for r in supporting],
            "contradicting": [r['source'] for r in contradicting],
            "neutral": [r['source'] for r in neutral],
            "recommendation": recommendation
        }


# Factory function
def create_capability(**kwargs) -> Capability:
    return FactChecker(**kwargs)

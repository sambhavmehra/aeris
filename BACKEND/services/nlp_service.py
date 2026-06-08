"""
AERIS AI OS - NLP Service
Provides advanced NLP capabilities: Named Entity Recognition, Tokenization,
Parts-of-Speech Tagging, and Sentiment Analysis.
"""
import logging
from typing import Dict, Any, List

import nltk
import spacy

logger = logging.getLogger("aeris.services.nlp")

# Download required NLTK resources if not already present
try:
    nltk.data.find("sentiment/vader_lexicon")
except LookupError:
    try:
        nltk.download("vader_lexicon", quiet=True)
    except Exception as e:
        logger.warning(f"Failed to download NLTK vader_lexicon: {e}")

try:
    from nltk.sentiment import SentimentIntensityAnalyzer
    _sia = SentimentIntensityAnalyzer()
except Exception as e:
    logger.warning(f"Failed to initialize NLTK SentimentIntensityAnalyzer: {e}")
    _sia = None

# Load SpaCy English model
try:
    _nlp = spacy.load("en_core_web_sm")
except Exception as e:
    logger.error(f"Failed to load SpaCy model 'en_core_web_sm': {e}")
    _nlp = None


class NLPService:
    """Service wrapping NLP libraries for advanced text analysis."""

    def __init__(self):
        pass

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """
        Perform a full NLP analysis on the provided text.
        Includes Sentiment, Entities, Tokens, and Key Phrases.
        """
        if not text or not text.strip():
            return {"error": "Empty text provided."}

        results: Dict[str, Any] = {
            "sentiment": {"pos": 0.0, "neg": 0.0, "neu": 0.0, "compound": 0.0, "label": "neutral"},
            "entities": [],
            "key_phrases": [],
            "tokens": []
        }

        # 1. Sentiment Analysis via NLTK VADER
        if _sia:
            try:
                scores = _sia.polarity_scores(text)
                results["sentiment"].update(scores)
                # Assign label
                comp = scores.get("compound", 0.0)
                if comp >= 0.05:
                    results["sentiment"]["label"] = "positive"
                elif comp <= -0.05:
                    results["sentiment"]["label"] = "negative"
                else:
                    results["sentiment"]["label"] = "neutral"
            except Exception as e:
                logger.warning(f"Sentiment analysis failed: {e}")

        # 2. SpaCy parsing for Entities, Tokens, and Chunks
        if _nlp:
            try:
                doc = _nlp(text)
                
                # Extract Named Entities
                for ent in doc.ents:
                    results["entities"].append({
                        "text": ent.text,
                        "label": ent.label_,
                        "start": ent.start_char,
                        "end": ent.end_char
                    })

                # Extract Key Noun Phrases
                for chunk in doc.noun_chunks:
                    # Ignore short/pronoun chunks to keep it clean
                    if len(chunk.text.split()) > 1 or chunk.root.pos_ not in ("PRON"):
                        results["key_phrases"].append(chunk.text.strip())
                # Deduplicate key phrases
                results["key_phrases"] = list(dict.fromkeys(results["key_phrases"]))[:15]

                # Extract top 20 tokens with POS tags (excluding stop words/punctuation)
                token_count = 0
                for token in doc:
                    if not token.is_stop and not token.is_punct and token_count < 20:
                        results["tokens"].append({
                            "word": token.text,
                            "lemma": token.lemma_,
                            "pos": token.pos_,
                            "tag": token.tag_
                        })
                        token_count += 1
            except Exception as e:
                logger.warning(f"SpaCy analysis failed: {e}")

        return results


# Singleton instance
nlp_service = NLPService()

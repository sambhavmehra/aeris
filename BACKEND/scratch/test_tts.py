import sys
import os
import logging

# Add BACKEND to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.DEBUG)
from services.texttospeech import text_to_speech

print("Testing TTS with Madhur neural voice...")
success = text_to_speech("Hello Sir, how are you? Testing the new text to speech system.")
print(f"TTS execution success: {success}")

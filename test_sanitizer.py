from ai_engine.trait_extractor import PersonalityTraitExtractor
from ai_engine.ollama_client import OllamaClient
import json

extractor = PersonalityTraitExtractor(OllamaClient('http://localhost:11434', 'test', 120), [], [], 50)
test_json = '{"quote": "It\'s about proving yourself, of staking your claim in a world that can, at times, feel surprisingly clamorous."}'
sanitized = extractor._sanitize_json_string(test_json)
print('Original:', repr(test_json))
print('Sanitized:', repr(sanitized))
try:
    full_json = '{' + sanitized + '}'
    parsed = json.loads(full_json)
    print('Parsed successfully')
except Exception as e:
    print('Parse failed:', e)
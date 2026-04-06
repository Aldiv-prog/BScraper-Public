import json
from datetime import datetime

# Read raw response
with open('logs/ai_engine_trait_response_raw.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# Get last response
responses = content.split('--- NEW RESPONSE ---')
last_resp = responses[-1].replace('--- END RESPONSE ---', '').strip()

# Convert smart quotes
last_resp = last_resp.replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'")

# Parse
data = json.loads(last_resp)
traits_list = data.get('traits', []) if isinstance(data, dict) else data

# Filter by threshold
filtered = [t for t in traits_list if t.get('confidence', 0) >= 50]

print(f'Parsed {len(traits_list)} total')
print(f'Filtered {len(filtered)} above 50%')
print('\nTraits:')
for t in filtered:
    print(f"  {t['name']}: {t['confidence']}%")

# Save
output = {
    'traits': filtered,
    'summary_reference': 'output/essay.md',
    'generated_at': datetime.now().isoformat(),
    'total_identified': len(filtered),
    'expected_total': 20
}

with open('output/traits.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print('\nUpdated traits.json successfully!')

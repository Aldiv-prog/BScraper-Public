#!/usr/bin/env python3
"""Extract traits from raw response logs and update traits.json."""

import json
from datetime import datetime

# Read the raw response
with open('logs/ai_engine_trait_response_raw.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# Get the last response
responses = content.split('--- NEW RESPONSE ---')
last_response = responses[-1].strip()

# Remove any trailing "--- END RESPONSE ---" marker
last_response = last_response.replace('--- END RESPONSE ---', '').strip()

# Convert smart quotes to regular quotes for parsing
last_response = last_response.replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'")

# Try to parse as JSON
try:
    data = json.loads(last_response)
    if isinstance(data, dict) and 'traits' in data:
        traits_list = data['traits']
    else:
        traits_list = data if isinstance(data, list) else []
    
    print(f"Successfully parsed {len(traits_list)} traits from raw response")
    
    # Filter by confidence threshold (50%)
    threshold = 50
    filtered_traits = [t for t in traits_list if isinstance(t, dict) and t.get('confidence', 0) >= threshold]
    
    print(f"Filtered to {len(filtered_traits)} traits above {threshold}% confidence")
    print("\nExtracted traits:")
    for trait in filtered_traits:
        print(f"  - {trait.get('name', 'Unknown')}: {trait.get('confidence', 0)}%")
    
    # Create the output structure
    output = {
        'traits': filtered_traits,
        'summary_reference': 'output\\essay.md',
        'generated_at': datetime.now().isoformat(),
        'total_identified': len(filtered_traits),
        'expected_total': 20
    }
    
    # Write to traits.json
    with open('output/traits.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nSuccessfully updated traits.json with {len(filtered_traits)} traits")
    
except json.JSONDecodeError as e:
    print(f"JSON parsing error: {e}")
    print(f"Error at position {e.pos}")
    print(f"Context: {last_response[max(0, e.pos-100):e.pos+100]}")
except Exception as e:
    print(f"Error: {e}")

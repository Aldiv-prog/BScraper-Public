#!/usr/bin/env python3
"""Debug bdsmlr.com login form structure."""

from scraper.session_manager import SessionManager
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.DEBUG)

# Create session and fetch login page manually
sm = SessionManager(
    base_url='https://bdsmlr.com',
    proxy_url='http://192.168.0.132:3128',
    verify_ssl=False
)

# Fetch login page
response = sm.session.get('https://bdsmlr.com/login', timeout=10)
print(f'Status: {response.status_code}')
print(f'URL: {response.url}')
print(f'Content length: {len(response.text)}')

# Parse the page
soup = BeautifulSoup(response.text, 'html.parser')
forms = soup.find_all('form')
print(f'Found {len(forms)} forms')

for i, form in enumerate(forms):
    print(f'\nForm {i+1}:')
    print(f'  Action: {form.get("action")}')
    print(f'  Method: {form.get("method")}')

    inputs = form.find_all('input')
    for inp in inputs:
        name = inp.get('name')
        type_ = inp.get('type')
        value = inp.get('value', '')[:50]  # Truncate long values
        if name:
            print(f'  Input: {name} (type: {type_}) value: {value}')

# Also check for any meta tags or scripts that might indicate CSRF
csrf_meta = soup.find('meta', attrs={'name': 'csrf-token'})
if csrf_meta:
    print(f'\nCSRF meta token: {csrf_meta.get("content")}')

# Check for any hidden inputs that might be CSRF tokens
hidden_inputs = soup.find_all('input', attrs={'type': 'hidden'})
for hidden in hidden_inputs:
    name = hidden.get('name')
    value = hidden.get('value', '')[:50]
    if name:
        print(f'Hidden input: {name} = {value}')
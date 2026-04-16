import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protonlaunch.helpers.helpers import steam_search
print('Import works!')
print('Testing Steam search...')
results = steam_search('witcher')
print(f'Found {len(results)} results')
for r in results[:3]:
    print(f"  - {r.get('name', 'Unknown')}")

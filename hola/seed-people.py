"""Create/update the five synthetic demo people through the authenticated API."""
import json
import os
import urllib.request
from pathlib import Path

base = os.environ.get('CONTEXT_API_URL', 'http://127.0.0.1:8090')
headers = {'Authorization': 'Bearer '+os.environ['CONTEXT_ADMIN_TOKEN'],
           'Content-Type': 'application/json'}
profiles = json.loads(Path(__file__).with_name('demo-people.json').read_text())
for person in profiles:
    person_id = person['id']
    body = {key: value for key, value in person.items() if key not in ('id', 'phone_env')}
    body['phone'] = os.environ.get(person['phone_env'])
    request = urllib.request.Request(base+'/people/'+person_id,
        data=json.dumps(body).encode(), headers=headers, method='PUT')
    with urllib.request.urlopen(request, timeout=10) as response:
        assert json.load(response)['id'] == person_id
    print(json.loads(person['initial_data'])['name']+': '+person_id)

"""Create missing local configuration without replacing existing credentials."""
import getpass
import ipaddress
import os
from pathlib import Path
import secrets


def main():
    path = Path(__file__).resolve().parent.parent / '.env'
    existing = set()
    if path.exists():
        existing = {line.split('=', 1)[0].strip() for line in path.read_text().splitlines()
                    if '=' in line and not line.lstrip().startswith('#')}
    values = {}
    prompts = {
        'HOLA_HOST_IP': 'This computer’s LAN IPv4 address',
        'OPENAI_API_KEY': 'OpenAI API key (with GPT-Live access)',
        'ORANGE_AUTH_USERNAME': 'Orange SIP username',
        'ORANGE_PASSWORD': 'Orange SIP password',
        'ORANGE_FROM_NUMBER': 'Orange phone number (+country code)',
    }
    for key, prompt in prompts.items():
        if key in existing:
            continue
        read = getpass.getpass if key in ('OPENAI_API_KEY', 'ORANGE_PASSWORD') else input
        value = read(prompt + ': ').strip()
        if not value:
            raise SystemExit(f'{key} is required; configuration was not written')
        if key == 'HOLA_HOST_IP':
            address = ipaddress.IPv4Address(value)
            if address.is_loopback or address.is_unspecified:
                raise SystemExit('Use your LAN address, not localhost or 0.0.0.0')
        values[key] = value
    for key in ('LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'CONTEXT_READ_TOKEN',
                'CONTEXT_ADMIN_TOKEN', 'CALL_WRITE_TOKEN'):
        if key not in existing:
            values[key] = secrets.token_hex(32)
    if values:
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), 'a') as file:
            file.write('\n')
            for key, value in values.items():
                quoted = value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '$$')
                file.write(f'{key}="{quoted}"\n')
        path.chmod(0o600)
    print('Configuration ready. Run: docker compose up -d --build')


if __name__ == '__main__':
    main()

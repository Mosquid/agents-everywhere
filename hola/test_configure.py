import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import configure


class ConfigureTest(unittest.TestCase):
    def test_preserves_existing_key_and_generates_private_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = root / '.env'
            env.write_text('OPENAI_API_KEY=existing-key\n')
            with patch.object(configure, '__file__', str(root / 'hola/configure.py')), \
                 patch('builtins.input', side_effect=['10.0.0.2', 'test-user', '+12025550123']), \
                 patch('getpass.getpass', return_value='test-password'):
                configure.main()
            text = env.read_text()
            self.assertEqual(text.count('OPENAI_API_KEY='), 1)
            self.assertIn('OPENAI_API_KEY=existing-key', text)
            generated = [line.split('=', 1)[1] for line in text.splitlines()
                         if line.startswith(('CONTEXT_', 'CALL_WRITE_TOKEN=', 'LIVEKIT_'))]
            self.assertEqual(len(generated), 5)
            self.assertEqual(len(set(generated)), 5)
            if os.name != 'nt':
                self.assertEqual(env.stat().st_mode & 0o777, 0o600)
            with patch.object(configure, '__file__', str(root / 'hola/configure.py')), \
                 patch('builtins.input', side_effect=AssertionError('Unexpected prompt')), \
                 patch('getpass.getpass', side_effect=AssertionError('Unexpected prompt')):
                configure.main()
            self.assertEqual(env.read_text(), text)

    def test_invalid_host_does_not_write_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(configure, '__file__', str(root / 'hola/configure.py')), \
                 patch('builtins.input', return_value='127.0.0.1'):
                with self.assertRaises(SystemExit):
                    configure.main()
            self.assertFalse((root / '.env').exists())

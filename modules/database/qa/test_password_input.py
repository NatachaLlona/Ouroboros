"""Password editing and fail-closed terminal fallback without database access."""
import contextlib
import io
import os
import unittest
from unittest.mock import patch
import warnings

from database import secrets
from database.settings import ConfigurationError


class Terminal(io.StringIO):
    def isatty(self):
        return True


class PasswordInputTests(unittest.TestCase):
    def test_asterisks_backspace_and_enter(self):
        stream = Terminal()
        characters = iter('\bAa12x\b345!\r')
        value = secrets._read_masked(lambda: next(characters), stream)
        self.assertEqual(value, 'Aa12345!')
        self.assertEqual(stream.getvalue(), '*****\b \b****\n')
        self.assertNotIn(value, stream.getvalue())

    def test_empty_enter_and_cancellation(self):
        stream = Terminal()
        self.assertEqual(secrets._read_masked(lambda: '\n', stream), '')
        for cancel in ('\x03', '\x04', '\x1b'):
            characters = iter('Ab'+cancel)
            stream = Terminal()
            with self.assertRaises(KeyboardInterrupt):
                secrets._read_masked(lambda: next(characters), stream)
            self.assertEqual(stream.getvalue(), '**\n')

    def test_all_bootstrap_labels_and_confirmations_use_shared_reader(self):
        for label in ('New PostgreSQL Master Password', 'New App Password'):
            characters = iter('Aa12345!\rAa12345!\r')
            stream = Terminal()
            with patch.object(secrets.os, 'name', 'nt'), patch.object(secrets, '_windows_reader', return_value=lambda: next(characters)), patch.object(secrets.sys, 'stdin', Terminal()), patch.object(secrets.sys, 'stdout', stream):
                self.assertEqual(secrets.prompt_password(label), 'Aa12345!')
            self.assertEqual(stream.getvalue(), label+': ********\nConfirm '+label+': ********\n')
            self.assertNotIn('Aa12345!', stream.getvalue())

    def test_powershell_and_vscode_use_same_windows_console_path(self):
        for environment in ({'PSModulePath':'test'}, {'TERM_PROGRAM':'vscode'}):
            characters = iter('Aa12345!\r')
            stream = Terminal()
            with patch.dict(os.environ, environment), patch.object(secrets.os,'name','nt'), patch.object(secrets,'_windows_reader',return_value=lambda: next(characters)), patch.object(secrets.sys,'stdin',Terminal()), patch.object(secrets.sys,'stdout',stream):
                self.assertEqual(secrets.read_password('App Password: '),'Aa12345!')
            self.assertEqual(stream.getvalue(), 'App Password: ********\n')

    def test_unsupported_masking_uses_hidden_input(self):
        with patch.object(secrets.os,'name','nt'), patch.object(secrets,'_windows_reader',return_value=None), patch.object(secrets.sys,'stdin',Terminal()), patch.object(secrets.sys,'stdout',Terminal()), patch.object(secrets.getpass,'getpass',return_value='Aa12345!') as hidden:
            self.assertEqual(secrets.read_password('App Password: '),'Aa12345!')
            hidden.assert_called_once_with('App Password: ')

    def test_visible_getpass_fallback_is_rejected(self):
        def insecure(prompt):
            warnings.warn('Echo would be enabled', secrets.getpass.GetPassWarning)
            self.fail('Visible input must never be reached')
        with patch.object(secrets.sys,'stdin',Terminal()), patch.object(secrets.sys,'stdout',io.StringIO()), patch.object(secrets.getpass,'getpass',side_effect=insecure):
            with self.assertRaises(ConfigurationError):
                secrets.read_password('App Password: ')

    def test_redirected_input_is_rejected_without_reading(self):
        with patch.object(secrets.sys,'stdin',io.StringIO('must not be read')), patch.object(secrets.getpass,'getpass') as hidden:
            with self.assertRaises(ConfigurationError):
                secrets.read_password('App Password: ')
            hidden.assert_not_called()

    def test_validation_and_confirmation_are_preserved(self):
        for values in (['short'], ['Aa12345!', 'Aa12346!']):
            with patch.object(secrets,'read_password',side_effect=values):
                with self.assertRaises(ConfigurationError):
                    secrets.prompt_password('New App Password')


if __name__ == '__main__':
    unittest.main()

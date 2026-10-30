"""Stream, cancellation, error-catalogue and DST boundary checks."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock
from app.audit_context import audit_context
from app.audit_middleware import RequestAuditingMiddleware
from app.audit_privacy import BodyCapture
from app.config import ConfigurationError, PROJECT_ROOT
from app.datetimes import source_values, present
from app.errors import load_error_codes


class AuditBoundaryTests(unittest.TestCase):
    def test_streams_cancellation_and_actual_headers(self):
        async def check(mode):
            saved, sent, received = [], [], []
            store = Mock()
            store.begin.return_value = 'AL0000001'
            store.finish.side_effect = lambda state, **facts: saved.append((state.error_code, facts))
            chunks = [b'{"value":', b'"' + b'x' * 400 + b'"}']
            incoming = iter([{'type':'http.request','body':part,'more_body':index == 0} for index,part in enumerate(chunks)])
            async def receive(): return next(incoming)
            async def send(message):
                if mode == 'send_failure': raise OSError('private transport detail')
                sent.append(message)
            async def downstream(scope, receive, send):
                for part in chunks:
                    received.append((await receive())['body'])
                if mode == 'before': raise RuntimeError('private internal detail')
                if mode == 'cancel_before': raise asyncio.CancelledError
                await send({'type':'http.response.start','status':202,'headers':[(b'content-type',b'application/json')]})
                await send({'type':'http.response.body','body':chunks[0],'more_body':True})
                if mode == 'after': raise RuntimeError('private internal detail')
                if mode == 'cancel_after': raise asyncio.CancelledError
                await send({'type':'http.response.body','body':chunks[1]})
            middleware = RequestAuditingMiddleware(downstream, None, Mock(), {'audit':{'request_body_max_bytes':256,'response_body_max_bytes':256}}, store=store)
            scope = {'type':'http','path':'/test','method':'POST','headers':[(b'content-type',b'application/json')]}
            try:
                await middleware(scope, receive, send)
            except (RuntimeError, asyncio.CancelledError) as failure:
                self.assertNotIn('private', str(failure))
            self.assertEqual(received,chunks)
            self.assertEqual(len(saved),1)
            code, facts = saved[0]
            self.assertEqual(facts['http_status'],None if mode in ('send_failure','cancel_before') else 500 if mode == 'before' else 202)
            self.assertEqual(facts['status'],'success' if mode == 'normal' else 'failure')
            self.assertLessEqual(sum(message['type']=='http.response.start' for message in sent),1)
            self.assertTrue(facts['capture']['request']['truncated'])
            self.assertIsNone(facts['request_body'])
            if mode == 'normal':
                self.assertEqual(b''.join(m.get('body',b'') for m in sent),b''.join(chunks))
                self.assertTrue(facts['capture']['response']['truncated'])
            if mode.startswith('cancel'): self.assertEqual(code,'REQUEST_CANCELLED')
            self.assertIsNone(audit_context.get())
        for mode in ('normal','before','after','cancel_before','cancel_after','send_failure'):
            asyncio.run(check(mode))

    def test_catalogue_validation_and_sensitive_capture(self):
        document = (PROJECT_ROOT / 'app/error_codes.json').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'codes.json'
            for content in ('{}', document.replace('"version": 1','"version": 2'), document.replace('"version": 1','"version": 1, "version": 1')):
                path.write_text(content,encoding='utf-8')
                with self.assertRaises(ConfigurationError): load_error_codes(path)
        capture = BodyCapture(256,'sensitive_operation')
        capture.feed(b'{"password":"private"}',True)
        self.assertEqual(len(capture.data),0)
        self.assertEqual(capture.result()[1]['reason'],'sensitive_operation')
        from app.audit_privacy import bounded_value
        safe, flags = bounded_value({'ordinary':'host=localhost dbname=private_db user=private_user password=private_password'},256)
        self.assertNotIn('private_',str(safe))
        safe, flags = bounded_value({'password=private_key':'private_value'},256)
        self.assertNotIn('private_',str(safe))
        safe, flags = bounded_value({'ordinary':'$argon2id$v=19$m=65536,t=3,p=4$private_salt$private_hash'},256)
        self.assertNotIn('private_',str(safe))

    def test_dst_offsets_unknown_original_and_no_geographic_inference(self):
        for value in ('2026-03-29T01:30:00+00:00','2026-03-29T01:30:00+01:00'):
            with self.assertRaises(ValueError): source_values(datetime.fromisoformat(value),'Europe/Lisbon')
        instants = [source_values(datetime.fromisoformat('2026-10-25T01:30:00' + offset),'Europe/Lisbon')[0] for offset in ('+01:00','+00:00')]
        self.assertNotEqual(*instants)
        canonical, offset, zone = source_values(datetime.fromisoformat('2026-07-01T12:00:00+01:00'))
        self.assertIsNone(zone)
        self.assertEqual(offset,'+01:00')
        shown = present({'watched_at':canonical},'original')['presentation']['dates']['watched_at']
        self.assertTrue(shown['fallback_utc'])
        shown = present({'watched_at':canonical,'watched_at_offset':offset},'original')['presentation']['dates']['watched_at']
        self.assertEqual(shown['timezone'],'+01:00')
        self.assertFalse(shown['fallback_utc'])

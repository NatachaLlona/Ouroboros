"""Calendar boundary regressions without connecting to normal storage."""
from datetime import datetime, timedelta, timezone
import unittest
from pydantic import ValidationError
from app.datetimes import date_predicates
from app.schemas.catalogue import RESOURCES
from app.schemas.test import TestQuery, TestBulkQuery
from app.schemas.audit import AuditFilters
from app.database_test import test_filters
from app.catalogue_repository import CatalogueRepository, CatalogueError


class DateFilterTests(unittest.TestCase):
    def bounds(self, **values):
        selection = TestQuery(**values)
        return [p[2] for p in date_predicates(selection.model_dump(), ('created_at',))]

    def test_whole_day_dst_and_inclusive_range(self):
        for day, hours in [('2026-03-29', 23), ('2026-10-25', 25)]:
            start, end = self.bounds(created_at_date=day, filter_timezone='Europe/Lisbon')
            self.assertEqual((end-start).total_seconds(), hours*3600)
            self.assertEqual(self.bounds(created_at_from=day, created_at_to=day, filter_timezone='Europe/Lisbon'), [start,end])
            self.assertLessEqual(start, end-timedelta(microseconds=1))
        start, end = self.bounds(created_at_from='2026-10-01',created_at_to='2026-10-25')
        self.assertEqual(start.isoformat(), '2026-09-30T23:00:00+00:00')
        self.assertEqual(end.isoformat(), '2026-10-26T00:00:00+00:00')
        self.assertEqual((self.bounds(created_at_date='2026-03-08',filter_timezone='America/New_York')[1]-self.bounds(created_at_date='2026-03-08',filter_timezone='America/New_York')[0]).total_seconds(), 23*3600)

    def test_open_bounds_timestamp_compatibility_and_default(self):
        self.assertIsNone(self.bounds(created_at_from='2026-10-25')[1])
        self.assertIsNone(self.bounds(created_at_to='2026-10-25')[0])
        start, end = self.bounds(created_at_from='2026-10-25T01:00:00+01:00',created_at_to='2026-10-25T01:00:00Z')
        self.assertEqual((end-start).total_seconds(),3600)
        selected = TestQuery(created_at_date='2026-10-25',display_timezone='Asia/Tokyo')
        selected.bind_filter_timezone({'application_timezone':'America/New_York'})
        self.assertEqual(date_predicates(selected.model_dump(),('created_at',))[0][2].hour,4)
        mixed = TestQuery(created_at_from='2026-10-25',created_at_to='2026-10-25T03:00:00Z')
        with self.assertRaises(CatalogueError):
            mixed.bind_filter_timezone({'application_timezone':'America/New_York'})

    def test_invalid_conflicting_and_naive(self):
        for values in [dict(created_at_date='2026-02-30'),dict(created_at_date='2026-1-01'),dict(created_at_date='2026-10-25T00:00:00Z'),dict(created_at_from='2026-10-25T00:00:00'),dict(created_at_to='2026-02-30'),dict(created_at_from='2026-10-26',created_at_to='2026-10-25'),dict(created_at_date='2026-10-25',created_at_from='2026-10-01'),dict(created_at_date='2026-10-25',created_at_to='2026-10-25'),dict(filter_timezone='original'),dict(filter_timezone='../UTC'),dict(created_at_to='9999-12-31')]:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                TestQuery(**values)

    def test_all_fields_share_bulk_and_read_predicates(self):
        for resource in RESOURCES.values():
            for field in ('created_at','added_at','watched_at'):
                if field not in resource.columns:
                    continue
                criteria = {field+'_date':'2026-10-25','filter_timezone':'Europe/Lisbon'}
                read = resource.query(**criteria)
                bulk = resource.bulk_query(**criteria,dry_run=True)
                repository = CatalogueRepository(None,resource)
                self.assertEqual(repository.filters(read.model_dump()),repository.filters(bulk.model_dump()))
                active = [p for p in repository.filters(read.model_dump()) if p[2] is not None]
                self.assertEqual([p[:2] for p in active],[(field,'>='),(field,'<')])
        criteria = dict(created_at_date='2026-10-25',filter_timezone='Europe/Lisbon')
        self.assertEqual(test_filters(TestQuery(**criteria).model_dump()),test_filters(TestBulkQuery(**criteria,dry_run=True).model_dump()))
        audit = AuditFilters(started_at_date='2026-10-25',finished_at_to='2026-10-25')
        self.assertEqual(len([p for p in date_predicates(audit.model_dump(),('started_at','finished_at')) if p[2] is not None]),3)

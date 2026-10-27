from datetime import datetime, timedelta

import pytest
from pytz import UTC

import uber
from uber.config import c
from uber.models import Attendee, Group, Session
from uber.utils import localized_now, request_cached_context


class TestPrices:
    def test_initial_attendee(self, clear_price_bumps):
        assert 40 == c.get_attendee_price(datetime.now(UTC))

    def test_group_member(self, clear_price_bumps):
        assert 30 == c.get_group_price(datetime.now(UTC))


class TestPriceBumps:
    @pytest.fixture(autouse=True)
    def add_price_bump_day(request, monkeypatch):
        monkeypatch.setattr(c, 'PRICE_BUMPS', {(datetime.now(UTC) - timedelta(days=1)): 50})
        monkeypatch.setattr(c, 'PRICE_LIMITS', {})

    def test_after_date_price_bump(self):
        assert 50 == c.get_attendee_price(datetime.now(UTC))

    def test_before_date_no_price_bump(self):
        assert 40 == c.get_attendee_price((datetime.now(UTC) - timedelta(days=2)))

    def test_on_date_no_price_bump(self):
        assert 40 == c.get_attendee_price((datetime.now(UTC) - timedelta(days=1, hours=2)))


class TestPriceLimits:
    @pytest.fixture(autouse=True)
    def add_price_bump_limit(request, monkeypatch):
        monkeypatch.setattr(c, 'PRICE_LIMITS', {1: 50})
        monkeypatch.setattr(c, 'PRICE_BUMPS', {})

    def test_under_limit_no_price_bump(self):
        assert 40 == c.get_attendee_price()

    def test_over_limit_price_bump_before_event(self, monkeypatch):
        monkeypatch.setattr(c, 'EPOCH', localized_now() + timedelta(days=1))
        session = Session().session
        assert c.BADGES_SOLD == 0

        with request_cached_context():
            session.add(Attendee(paid=c.HAS_PAID, badge_status=c.COMPLETED_STATUS))
            session.commit()

        assert c.BADGES_SOLD == 1
        assert 50 == c.get_attendee_price()

    def test_over_limit_price_bump_during_event(self, monkeypatch):
        monkeypatch.setattr(c, 'EPOCH', localized_now() - timedelta(days=1))

        session = Session().session
        assert c.BADGES_SOLD == 0

        with request_cached_context():
            session.add(Attendee(paid=c.HAS_PAID, badge_status=c.COMPLETED_STATUS))
            session.commit()

        assert c.BADGES_SOLD == 1
        assert 40 == c.get_attendee_price()

    def test_refunded_badge_price_bump_before_event(self, monkeypatch):
        monkeypatch.setattr(c, 'EPOCH', localized_now() + timedelta(days=1))
        session = Session().session
        assert c.BADGES_SOLD == 0

        with request_cached_context():
            session.add(Attendee(paid=c.REFUNDED, badge_status=c.COMPLETED_STATUS))
            session.commit()

        assert c.BADGES_SOLD == 1
        assert 50 == c.get_attendee_price()

    def test_refunded_badge_price_bump_during_event(self, monkeypatch):
        monkeypatch.setattr(c, 'EPOCH', localized_now() - timedelta(days=1))
        session = Session().session
        assert c.BADGES_SOLD == 0

        with request_cached_context():
            session.add(Attendee(paid=c.REFUNDED, badge_status=c.COMPLETED_STATUS))
            session.commit()

        assert c.BADGES_SOLD == 1
        assert 40 == c.get_attendee_price()

    def test_invalid_badge_no_price_bump(self):
        session = Session().session
        assert c.BADGES_SOLD == 0

        with request_cached_context():
            session.add(Attendee(paid=c.HAS_PAID, badge_status=c.INVALID_STATUS))
            session.commit()

        assert c.BADGES_SOLD == 0
        assert 40 == c.get_attendee_price()

    def test_free_badge_no_price_bump(self):
        session = Session().session
        assert c.BADGES_SOLD == 0

        with request_cached_context():
            session.add(Attendee(paid=c.NEED_NOT_PAY, badge_status=c.COMPLETED_STATUS))
            session.commit()

        assert c.BADGES_SOLD == 0
        assert 40 == c.get_attendee_price()

    # todo: Test badges that are paid by group


class TestBadgePriceEstimate:
    @pytest.fixture(autouse=True)
    def add_price_limits(request, monkeypatch):
        monkeypatch.setattr(c, 'PRICE_LIMITS', {1000: 50, 2500: 55})
        monkeypatch.setattr(c, 'ORDERED_PRICE_LIMITS', [50, 55])
        monkeypatch.setattr(c, 'PRICE_BUMPS', {})

    def test_no_limits_estimate_no_max(self, monkeypatch):
        monkeypatch.setattr(c, 'ORDERED_PRICE_LIMITS', [])
        monkeypatch.setattr(c, 'MAX_BADGE_SALES', 0)
        assert -1 == c.BADGES_LEFT_AT_CURRENT_PRICE

    def test_no_limits_estimate_with_max(self, monkeypatch):
        monkeypatch.setattr(c, 'ORDERED_PRICE_LIMITS', [])
        monkeypatch.setattr(c, 'MAX_BADGE_SALES', 100)
        assert 100 == c.BADGES_LEFT_AT_CURRENT_PRICE

    def test_last_price_estimate_no_max(self, monkeypatch):
        monkeypatch.setattr(uber.config.Config, 'BADGE_PRICE', 55)
        monkeypatch.setattr(c, 'MAX_BADGE_SALES', 0)
        assert -1 == c.BADGES_LEFT_AT_CURRENT_PRICE

    def test_last_price_estimate_with_max(self, monkeypatch):
        monkeypatch.setattr(uber.config.Config, 'BADGE_PRICE', 55)
        monkeypatch.setattr(c, 'MAX_BADGE_SALES', 100)
        assert 100 == c.BADGES_LEFT_AT_CURRENT_PRICE

    def test_almost_gone_estimate(self, monkeypatch):
        monkeypatch.setattr(uber.config.Config, 'BADGES_SOLD', 990)
        assert 10 == c.BADGES_LEFT_AT_CURRENT_PRICE

    def test_very_low_estimate(self, monkeypatch):
        monkeypatch.setattr(uber.config.Config, 'BADGES_SOLD', 910)
        assert 90 == c.BADGES_LEFT_AT_CURRENT_PRICE

    def test_low_estimate(self, monkeypatch):
        monkeypatch.setattr(uber.config.Config, 'BADGES_SOLD', 760)
        assert 240 == c.BADGES_LEFT_AT_CURRENT_PRICE

    def test_moderate_estimate(self, monkeypatch):
        monkeypatch.setattr(uber.config.Config, 'BADGES_SOLD', 600)
        assert 400 == c.BADGES_LEFT_AT_CURRENT_PRICE

    def test_high_estimate(self, monkeypatch):
        monkeypatch.setattr(uber.config.Config, 'BADGES_SOLD', 260)
        assert 740 == c.BADGES_LEFT_AT_CURRENT_PRICE

    def test_very_high_estimate(self, monkeypatch):
        monkeypatch.setattr(uber.config.Config, 'BADGES_SOLD', 60)
        assert 940 == c.BADGES_LEFT_AT_CURRENT_PRICE

    def test_super_high_estimate(self, monkeypatch):
        monkeypatch.setattr(uber.config.Config, 'BADGES_SOLD', 1010)
        monkeypatch.setattr(uber.config.Config, 'BADGE_PRICE', 50)
        assert 1490 == c.BADGES_LEFT_AT_CURRENT_PRICE


class TestBadgeOpts:
    def test_prereg_badge_opts_with_group(self, monkeypatch):
        monkeypatch.setattr(c, 'GROUP_PREREG_TAKEDOWN', localized_now() + timedelta(days=1))
        assert c.PREREG_BADGE_TYPES == [c.ATTENDEE_BADGE, c.PSEUDO_DEALER_BADGE, c.PSEUDO_GROUP_BADGE]

    def test_prereg_badge_opts_no_group(self):
        assert c.PREREG_BADGE_TYPES == [c.ATTENDEE_BADGE, c.PSEUDO_DEALER_BADGE]

    def test_prereg_badge_opts_with_extra(self, monkeypatch):
        monkeypatch.setattr(c, 'BADGE_TYPE_PRICES', {c.CONTRACTOR_BADGE: 55})
        assert c.PREREG_BADGE_TYPES == [c.ATTENDEE_BADGE, c.PSEUDO_DEALER_BADGE, c.CONTRACTOR_BADGE]

    def test_at_door_badge_opts_plain(self, monkeypatch):
        monkeypatch.setattr(c, 'ONE_DAYS_ENABLED', False)
        assert dict(c.AT_THE_DOOR_BADGE_OPTS).keys() == {c.ATTENDEE_BADGE}

    def test_at_door_badge_opts_simple_one_days(self):
        assert dict(c.AT_THE_DOOR_BADGE_OPTS).keys() == {c.ATTENDEE_BADGE, c.ONE_DAY_BADGE}

    def test_at_door_badge_opts_presold_one_days(self, monkeypatch):
        monkeypatch.setattr(c, 'PRESELL_ONE_DAYS', True)
        monday_after_now = localized_now() + timedelta(days=(7-localized_now().weekday()))
        monkeypatch.setattr(c, 'EPOCH', monday_after_now + timedelta(days=4))
        monkeypatch.setattr(c, 'ESCHATON', monday_after_now + timedelta(days=6))
        assert dict(c.AT_THE_DOOR_BADGE_OPTS).keys() == {c.ATTENDEE_BADGE, c.FRIDAY, c.SATURDAY, c.SUNDAY}

    def test_at_door_badge_opts_with_extra(self, monkeypatch):
        monkeypatch.setattr(c, 'BADGE_TYPE_PRICES', {c.CONTRACTOR_BADGE: 55})
        assert dict(c.AT_THE_DOOR_BADGE_OPTS).keys() == {c.ATTENDEE_BADGE, c.ONE_DAY_BADGE, c.CONTRACTOR_BADGE}


class TestDealerConfig:
    def test_dealer_reg_open(self, monkeypatch):
        monkeypatch.setattr(c, 'DEALER_REG_START', localized_now() - timedelta(days=1))
        monkeypatch.setattr(c, 'DEALER_REG_SHUTDOWN', localized_now() + timedelta(days=1))
        assert c.DEALER_REG_OPEN

    def test_dealer_reg_not_open_yet(self, monkeypatch):
        monkeypatch.setattr(c, 'DEALER_REG_START', localized_now() + timedelta(days=1))
        assert not c.DEALER_REG_OPEN

    def test_dealer_reg_closed(self, monkeypatch):
        monkeypatch.setattr(c, 'DEALER_REG_SHUTDOWN', localized_now() - timedelta(days=1))
        assert not c.DEALER_REG_OPEN

    def test_dealer_reg_not_soft_closed(self, monkeypatch):
        monkeypatch.setattr(c, 'DEALER_REG_DEADLINE', localized_now() + timedelta(days=1))
        monkeypatch.setattr(uber.config.Config, 'DEALER_APPS', 10)
        monkeypatch.setattr(c, 'MAX_DEALER_APPS', 100)
        assert not c.DEALER_REG_SOFT_CLOSED

    def test_dealer_reg_not_soft_closed_no_max(self, monkeypatch):
        monkeypatch.setattr(c, 'DEALER_REG_DEADLINE', localized_now() + timedelta(days=1))
        monkeypatch.setattr(uber.config.Config, 'DEALER_APPS', 10)
        monkeypatch.setattr(c, 'MAX_DEALER_APPS', 0)
        assert not c.DEALER_REG_SOFT_CLOSED

    def test_dealer_reg_soft_closed_over_max(self, monkeypatch):
        monkeypatch.setattr(c, 'DEALER_REG_DEADLINE', localized_now() + timedelta(days=1))
        monkeypatch.setattr(uber.config.Config, 'DEALER_APPS', 10)
        monkeypatch.setattr(c, 'MAX_DEALER_APPS', 1)
        assert c.DEALER_REG_SOFT_CLOSED

    def test_dealer_reg_soft_closed_at_max(self, monkeypatch):
        monkeypatch.setattr(c, 'DEALER_REG_DEADLINE', localized_now() + timedelta(days=1))
        monkeypatch.setattr(uber.config.Config, 'DEALER_APPS', 1)
        monkeypatch.setattr(c, 'MAX_DEALER_APPS', 1)
        assert c.DEALER_REG_SOFT_CLOSED

    def test_dealer_reg_soft_closed_after_deadline(self, monkeypatch):
        monkeypatch.setattr(c, 'DEALER_REG_DEADLINE', localized_now() - timedelta(days=1))
        monkeypatch.setattr(uber.config.Config, 'DEALER_APPS', 10)
        monkeypatch.setattr(c, 'MAX_DEALER_APPS', 100)
        assert c.DEALER_REG_SOFT_CLOSED

    def test_dealer_app(self):
        session = Session().session
        with request_cached_context():
            session.add(Group(tables=1, cost=10, status=c.UNAPPROVED))
            session.commit()

        assert c.DEALER_APPS == 1

    def test_waitlisted_dealer_not_app(self):
        session = Session().session
        with request_cached_context():
            session.add(Group(tables=1, cost=10, status=c.WAITLISTED))
            session.commit()

        assert c.DEALER_APPS == 0

    def test_free_dealer_no_app(self):
        session = Session().session
        with request_cached_context():
            session.add(Group(tables=1, cost=0, auto_recalc=False, status=c.UNAPPROVED))
            session.commit()

        assert c.DEALER_APPS == 0

    def test_not_a_dealer_no_app(self):
        session = Session().session
        with request_cached_context():
            session.add(Group(tables=0, cost=10, status=c.UNAPPROVED))
            session.commit()

        assert c.DEALER_APPS == 0

    def test_dealer_reg_soft_closed_per_type(self, monkeypatch):
        type_a, type_b = 101, 102
        monkeypatch.setattr(c, 'DEALER_REG_DEADLINE', localized_now() + timedelta(days=1))
        monkeypatch.setattr(c, 'MAX_DEALER_APPS', {type_a: 5, type_b: 2})
        monkeypatch.setattr(uber.config.Config, 'TABLE_TYPES', [type_a, type_b])
        monkeypatch.setattr(uber.config.Config, 'DEALER_APPS_BY_TYPE', {type_a: 4, type_b: 1})

        assert not c.is_dealer_type_soft_closed(type_a)
        assert not c.is_dealer_type_soft_closed(type_b)
        assert not c.DEALER_REG_SOFT_CLOSED

        # Cap reached for type_a only
        monkeypatch.setattr(uber.config.Config, 'DEALER_APPS_BY_TYPE', {type_a: 5, type_b: 1})
        assert c.is_dealer_type_soft_closed(type_a)
        assert not c.is_dealer_type_soft_closed(type_b)
        assert not c.DEALER_REG_SOFT_CLOSED

        # Both caps reached
        monkeypatch.setattr(uber.config.Config, 'DEALER_APPS_BY_TYPE', {type_a: 5, type_b: 2})
        assert c.is_dealer_type_soft_closed(type_a)
        assert c.is_dealer_type_soft_closed(type_b)
        assert c.DEALER_REG_SOFT_CLOSED

    def test_dealer_reg_soft_closed_per_type_uncapped(self, monkeypatch):
        type_a, type_b = 101, 102
        monkeypatch.setattr(c, 'DEALER_REG_DEADLINE', localized_now() + timedelta(days=1))
        monkeypatch.setattr(c, 'MAX_DEALER_APPS', {type_a: 5, type_b: 0})
        monkeypatch.setattr(uber.config.Config, 'TABLE_TYPES', [type_a, type_b])
        monkeypatch.setattr(uber.config.Config, 'DEALER_APPS_BY_TYPE', {type_a: 5, type_b: 100})

        assert c.is_dealer_type_soft_closed(type_a)
        assert not c.is_dealer_type_soft_closed(type_b)
        assert not c.DEALER_REG_SOFT_CLOSED

    def test_prereg_table_opts_per_type(self, monkeypatch):
        type_a, type_b = 101, 102
        monkeypatch.setattr(c, 'DEALER_REG_DEADLINE', localized_now() + timedelta(days=1))
        monkeypatch.setattr(c, 'MAX_DEALER_APPS', {type_a: 5, type_b: 2})
        monkeypatch.setattr(uber.config.Config, 'TABLE_OPTS', [(type_a, 'Artist Alley'), (type_b, 'Dealer Booth')])
        monkeypatch.setattr(c, 'VENDOR_PRICES', {type_a: 100, type_b: 250})

        # Under cap
        monkeypatch.setattr(uber.config.Config, 'DEALER_APPS_BY_TYPE', {type_a: 2, type_b: 1})
        opts = c.PREREG_TABLE_OPTS
        assert opts == [(type_a, 'Artist Alley, $100'), (type_b, 'Dealer Booth, $250')]
        assert c.AVAILABLE_PREREG_TABLE_OPTS == [(type_a, 'Artist Alley, $100'), (type_b, 'Dealer Booth, $250')]

        # type_a hits cap
        monkeypatch.setattr(uber.config.Config, 'DEALER_APPS_BY_TYPE', {type_a: 5, type_b: 1})
        opts = c.PREREG_TABLE_OPTS
        assert opts == [(type_a, 'Artist Alley, $100 (Waitlist)'), (type_b, 'Dealer Booth, $250')]
        assert c.AVAILABLE_PREREG_TABLE_OPTS == [(type_b, 'Dealer Booth, $250')]

    def test_get_max_dealer_apps(self, monkeypatch):
        # Dict config
        monkeypatch.setattr(c, 'MAX_DEALER_APPS', {101: 5, 102: 10})
        assert c.get_max_dealer_apps(101) == 5
        assert c.get_max_dealer_apps(102) == 10
        assert c.get_max_dealer_apps(999) == 0
        assert c.get_max_dealer_apps() == 15

        # Int config
        monkeypatch.setattr(c, 'MAX_DEALER_APPS', 25)
        assert c.get_max_dealer_apps(101) == 25
        assert c.get_max_dealer_apps() == 25

    def test_get_max_dealers(self, monkeypatch):
        # Dict config
        monkeypatch.setattr(c, 'MAX_DEALERS', {101: 2, 102: 6})
        assert c.get_max_dealers(101) == 2
        assert c.get_max_dealers(102) == 6
        assert c.get_max_dealers(999) == 0
        assert c.get_max_dealers() == 6

        # Int config
        monkeypatch.setattr(c, 'MAX_DEALERS', 20)
        assert c.get_max_dealers(101) == 20
        assert c.get_max_dealers() == 20

    def test_dealer_apps_by_type(self):
        session = Session().session
        with request_cached_context():
            session.add(Group(tables=101, cost=10, status=c.UNAPPROVED))
            session.add(Group(tables=101, cost=10, status=c.UNAPPROVED))
            session.add(Group(tables=102, cost=10, status=c.UNAPPROVED))
            session.commit()

        assert c.get_dealer_apps(101) == 2
        assert c.get_dealer_apps(102) == 1
        assert c.get_dealer_apps(999) == 0
        assert c.DEALER_APPS == 3


class TestMiscConfig:
    @pytest.mark.parametrize('cutoff,start,expected', [
        ('', '', False),
        ('', localized_now() - timedelta(days=1), False),
        (localized_now() + timedelta(days=3), localized_now() + timedelta(days=2), False),
        (localized_now() - timedelta(days=2), localized_now() + timedelta(days=3), False),
        (localized_now() + timedelta(days=3), '', True),
        (localized_now() + timedelta(days=3), localized_now() - timedelta(days=2), True),
    ])
    def test_self_service_refunds(self, monkeypatch, cutoff, start, expected):
        monkeypatch.setattr(c, 'REFUND_CUTOFF', cutoff)
        monkeypatch.setattr(c, 'REFUND_START', start)
        assert c.SELF_SERVICE_REFUNDS_OPEN == expected

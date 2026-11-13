from decimal import Decimal

import pytest

from accounts.models import Freelancer
from contracts.models import Contract
from django.contrib.auth.models import User


@pytest.fixture
def another_freelancer():
    user = User.objects.create_user(
        username='newbie@freelance.test', email='newbie@freelance.test', password='x'
    )
    return Freelancer.objects.create(user=user, name='Newbie Freelancer')


@pytest.mark.django_db
def test_create_contract_requires_auth(api_client, another_freelancer):
    resp = api_client.post('/api/contracts/', {
        'freelancer': another_freelancer.id,
        'daily_rate': '500.00',
        'start_date': '2026-01-01',
        'end_date': '2026-06-30',
        'status': 'active',
    })
    assert resp.status_code == 401


@pytest.mark.django_db
def test_admin_creates_contract_for_own_company(admin_client, admin_user, another_freelancer):
    resp = admin_client.post('/api/contracts/', {
        'freelancer': another_freelancer.id,
        'daily_rate': '550.00',
        'start_date': '2026-02-01',
        'end_date': '2026-08-31',
        'status': 'active',
    })
    assert resp.status_code == 201
    assert resp.data['company']['id'] == admin_user.company_admin.company.id
    assert resp.data['freelancer']['id'] == another_freelancer.id
    assert resp.data['status'] == 'active'

    contract = Contract.objects.get(pk=resp.data['id'])
    assert contract.company == admin_user.company_admin.company
    assert contract.daily_rate == Decimal('550.00')


@pytest.mark.django_db
def test_freelancer_cannot_create_contract(freelancer_client, another_freelancer):
    resp = freelancer_client.post('/api/contracts/', {
        'freelancer': another_freelancer.id,
        'daily_rate': '550.00',
        'start_date': '2026-02-01',
        'end_date': '2026-08-31',
        'status': 'active',
    })
    assert resp.status_code == 403
    assert not Contract.objects.exists()


@pytest.mark.django_db
def test_create_contract_rejects_end_before_start(admin_client, another_freelancer):
    resp = admin_client.post('/api/contracts/', {
        'freelancer': another_freelancer.id,
        'daily_rate': '550.00',
        'start_date': '2026-08-31',
        'end_date': '2026-02-01',
        'status': 'active',
    })
    assert resp.status_code == 400
    assert 'end_date' in resp.data
    assert not Contract.objects.exists()


@pytest.mark.django_db
def test_create_contract_ignores_company_in_body(admin_client, admin_user, meridian, another_freelancer):
    # The client should never be able to assign a contract to a company other than
    # the admin's own — even if it tries to via the request body.
    resp = admin_client.post('/api/contracts/', {
        'company': meridian.id,
        'freelancer': another_freelancer.id,
        'daily_rate': '550.00',
        'start_date': '2026-02-01',
        'end_date': '2026-08-31',
        'status': 'active',
    })
    assert resp.status_code == 201
    assert resp.data['company']['id'] == admin_user.company_admin.company.id
    assert resp.data['company']['id'] != meridian.id


@pytest.mark.django_db
def test_freelancer_list_requires_admin(freelancer_client):
    resp = freelancer_client.get('/api/freelancers/')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_admin_lists_freelancers(admin_client, another_freelancer):
    resp = admin_client.get('/api/freelancers/')
    assert resp.status_code == 200
    names = [f['name'] for f in resp.data]
    assert 'Newbie Freelancer' in names
    assert all({'id', 'name'} <= set(f.keys()) for f in resp.data)

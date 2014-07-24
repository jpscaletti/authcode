# coding=utf-8
from __future__ import print_function
import os

import authcode
from authcode._compat import to_unicode
from authcode.views import pop_next_url
from flask import Flask, request
from sqlalchemy_wrapper import SQLAlchemy

from helpers import SECRET_KEY


def test_pop_next_url():
    auth = authcode.Auth(SECRET_KEY)
    session = {auth.redirect_key: '/abc'}
    next_url = pop_next_url(auth, request, session)
    assert next_url == '/abc'

    auth.sign_in_redirect = '/test'
    next_url = pop_next_url(auth, request, {})
    assert next_url == auth.sign_in_redirect

    auth.sign_in_redirect = None
    next_url = pop_next_url(auth, request, {})
    assert next_url == '/'


def get_flask_app(roles=False, **kwargs):
    db = SQLAlchemy()
    auth = authcode.Auth(SECRET_KEY, db=db, roles=roles, **kwargs)
    User = auth.User

    db.create_all()
    user = User(login=u'meh', password='foobar')
    db.add(user)
    db.commit()

    app = Flask('test')
    app.secret_key = os.urandom(32)
    app.testing = True

    authcode.setup_for_flask(auth, app)
    auth.session = {}
    return auth, app, user


def test_login_view():
    auth, app, user = get_flask_app()
    client = app.test_client()

    r = client.get(auth.url_sign_in)
    assert u'Sign in' in to_unicode(r.data)

    r = client.post(auth.url_sign_in)
    assert u'<!-- ERROR -->' not in to_unicode(r.data)

    data = {
        '_csrf_token': auth.get_csrf_token(),
    }
    r = client.post(auth.url_sign_in, data=data)
    assert u'<!-- ERROR -->' in to_unicode(r.data)
    assert auth.session_key not in auth.session


def test_login_wrong_credentials():
    auth, app, user = get_flask_app()
    client = app.test_client()

    data = {
        'login': 'xxx',
        'password': 'zzz',
        '_csrf_token': auth.get_csrf_token(),
    }
    r = client.post(auth.url_sign_in, data=data)
    assert u'<!-- ERROR -->' in to_unicode(r.data)
    assert auth.session_key not in auth.session


def test_login_right_credentials():
    auth, app, user = get_flask_app()
    client = app.test_client()

    data = {
        'login': user.login,
        'password': 'foobar',
        '_csrf_token': auth.get_csrf_token(),
    }
    r = client.post(auth.url_sign_in, data=data)
    assert r.status == '303 SEE OTHER'
    assert auth.session_key in auth.session


def test_login_redirect_if_already_logged_in():
    auth, app, user = get_flask_app()
    client = app.test_client()
    auth.login(user)

    auth.session[auth.redirect_key] = 'http://google.com'
    r = client.get(auth.url_sign_in)
    assert r.status == '303 SEE OTHER'


def test_redirect_after_logout():
    auth, app, user = get_flask_app()
    client = app.test_client()
    auth.login(user)

    url = '{0}?_csrf_token={1}'.format(auth.url_sign_out, auth.get_csrf_token())
    r = client.get(url)
    assert r.status == '303 SEE OTHER'
    assert auth.session_key not in auth.session


def test_reset_password():
    auth, app, user = get_flask_app()
    client = app.test_client()
    log = []

    def send_email(user, subject, msg):
        log.append(msg)

    auth.send_email = send_email
    user.get_token()

    r = client.get(auth.url_reset_password)
    data = to_unicode(r.data)
    print(data)
    assert u'Reset password' in data


def test_reset_password_wrong_account():
    auth, app, user = get_flask_app()
    client = app.test_client()
    log = []

    def send_email(user, subject, msg):
        log.append(msg)

    auth.send_email = send_email
    user.get_token()

    data = dict(login=u'nn', _csrf_token=auth.get_csrf_token())
    r = client.post(auth.url_reset_password, data=data)
    data = to_unicode(r.data)
    print(data)
    assert u'<!-- ERROR NOT FOUND -->' in data


def test_reset_password_email_sent():
    auth, app, user = get_flask_app()
    client = app.test_client()
    log = []

    def send_email(user, subject, msg):
        log.append(msg)

    auth.send_email = send_email
    token = user.get_token()
    data = dict(login=user.login, _csrf_token=auth.get_csrf_token())
    r = client.post(auth.url_reset_password, data=data)
    data = to_unicode(r.data)
    assert u'<!-- EMAIL SENT -->' in data
    print(log)
    assert u'{0}{1}'.format(auth.url_reset_password, token[:5]) in log[0]


def test_reset_password_wrong_token():
    auth, app, user = get_flask_app()
    client = app.test_client()
    log = []

    def send_email(user, subject, msg):
        log.append(msg)

    auth.send_email = send_email
    user.get_token()
    r = client.get(auth.url_reset_password + 'xxx/')
    data = to_unicode(r.data)
    print(data)
    assert u'<!-- ERROR WRONG TOKEN -->' in data


def test_reset_password_good_token():
    auth, app, user = get_flask_app()
    client = app.test_client()
    log = []

    def send_email(user, subject, msg):
        log.append(msg)

    auth.send_email = send_email
    token = user.get_token()
    r = client.get(auth.url_reset_password + token + '/')
    data = to_unicode(r.data)
    assert auth.session_key in auth.session
    assert u'Change password' in data
    assert u'current password' not in data

    r = client.get(auth.url_reset_password)
    assert r.status == '303 SEE OTHER'


def test_change_password():
    auth, app, user = get_flask_app()
    client = app.test_client()

    r = client.get(auth.url_change_password)
    assert r.status == '303 SEE OTHER'

    auth.login(user)
    csrf_token = auth.get_csrf_token()

    r = client.get(auth.url_change_password)
    data = to_unicode(r.data)
    assert u'Change password' in data
    assert u'current password' in data

    r = client.post(auth.url_change_password, data=dict(
        np1='lalala', np2='lalala', _csrf_token=csrf_token))
    data = to_unicode(r.data)
    assert u'<!-- ERROR FAIL -->' in data

    r = client.post(auth.url_change_password, data=dict(
        password='lalala', np1='lalala', np2='lalala', _csrf_token=csrf_token))
    data = to_unicode(r.data)
    assert u'<!-- ERROR FAIL -->' in data

    r = client.post(auth.url_change_password, data=dict(
        password='foobar', np1='a', np2='a', _csrf_token=csrf_token))
    data = to_unicode(r.data)
    assert u'<!-- ERROR TOO SHORT -->' in data

    r = client.post(auth.url_change_password, data=dict(
        password='foobar', np1='lalalala', np2='a', _csrf_token=csrf_token))
    data = to_unicode(r.data)
    print(data)
    assert u'<!-- ERROR MISMATCH -->' in data

    r = client.post(auth.url_change_password, data=dict(
        password='foobar', np1='lalala', np2='lalala'))
    assert r.status == '403 FORBIDDEN'

    r = client.post(auth.url_change_password, data=dict(
        password='foobar', np1='lalala', np2='lalala', _csrf_token=csrf_token))
    data = to_unicode(r.data)
    assert u'<!-- PASSWORD UPDATED -->' in data
    assert user.has_password('lalala')

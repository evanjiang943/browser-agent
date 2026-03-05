"""Tests for web session management."""

import asyncio

from evidence_collector.web.session import Session, SessionManager


def test_session_defaults():
    s = Session(session_id="abc")
    assert s.phase == "chat"
    assert s.messages == []
    assert s.uploaded_file is None
    assert s.task is None
    assert s.run_task is None


def test_session_manager_create():
    mgr = SessionManager()
    s = mgr.create()
    assert len(s.session_id) == 12
    assert mgr.get(s.session_id) is s


def test_session_manager_remove():
    mgr = SessionManager()
    s = mgr.create()
    sid = s.session_id
    mgr.remove(sid)
    assert mgr.get(sid) is None


def test_session_manager_remove_nonexistent():
    mgr = SessionManager()
    mgr.remove("nonexistent")  # Should not raise


def test_session_manager_multiple():
    mgr = SessionManager()
    s1 = mgr.create()
    s2 = mgr.create()
    assert s1.session_id != s2.session_id
    assert mgr.get(s1.session_id) is s1
    assert mgr.get(s2.session_id) is s2

import pytest
import os
import pytest_cassandra


def test_pytest_cassandra_a(testdir):
    testdir.makepyfile('''
    import pytest
    from pytest_cassandra import session_cluster_fixture

    def test_a(session_cluster_fixture):
        assert len(session_cluster_fixture.hosts) == 3
    ''')
    result = testdir.runpytest('--with-cassandra')
    #result.assert_outcomes(passed=1)

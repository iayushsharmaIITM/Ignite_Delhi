"""Regression test pinning the connection pool ceiling.

Owner: Tomás Ferrer (SRE)
Added: 2026-07-14, following INC-4412.

WHY THIS TEST EXISTS
--------------------
INC-4412 was not caused by a logic bug. It was caused by deleting a single
configuration value (the connection pool ceiling) during an unrelated
performance change in pulse-api@v4.18.2. No test failed, because nothing
asserted that the ceiling was still there.

The On-Call Handbook v6.2 §5 now requires that any change to a resource
ceiling ships with a regression test that pins the previous value. This is
that test for the connection pool.

A future change may legitimately raise the ceiling - but it must edit this
test deliberately, which forces a reviewer to see it. That is the point.
"""

import pytest

from pulse_api.config import load_deploy_config

PROD_CONFIG = "deploy/prod/pulse-api.yaml"

# The value restored during the INC-4412 rollback. Do not change this without
# an approved RFC and a load test against promotion-window traffic.
EXPECTED_POOL_CEILING = 50


@pytest.fixture(scope="module")
def prod():
    return load_deploy_config(PROD_CONFIG)


def test_pool_ceiling_is_pinned(prod):
    """The exact failure mode of INC-4412: a missing ceiling, not a wrong one."""
    assert prod.database.connection_pool_ceiling is not None, (
        "connection_pool_ceiling is absent. This is the INC-4412 failure mode - "
        "the pool grows unbounded under peak traffic. See handbook §5."
    )


def test_pool_ceiling_matches_rollback_value(prod):
    assert prod.database.connection_pool_ceiling == EXPECTED_POOL_CEILING


def test_backpressure_prevents_cascade(prod):
    """A saturated pool must degrade ingestion, not take the dashboard down."""
    assert prod.ingestion.backpressure_enabled is True


def test_ingestion_workers_do_not_outnumber_pool(prod):
    """Workers holding connections must not exceed the ceiling, or they starve."""
    assert prod.ingestion.worker_count < prod.database.connection_pool_ceiling

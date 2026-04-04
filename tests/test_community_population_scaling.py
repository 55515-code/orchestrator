from __future__ import annotations

import unittest

from substrate.community import (
    DEVELOPER_COHORTS,
    USER_TESTER_COHORTS,
    _build_developer_agents,
    _build_user_tester_agents,
    _scale_cohorts,
)


class CommunityPopulationScalingTest(unittest.TestCase):
    def test_scale_cohorts_preserves_total_for_half_scale(self) -> None:
        scaled = _scale_cohorts(DEVELOPER_COHORTS, 0.5)
        self.assertEqual(50, sum(count for _, count in scaled))

    def test_scale_cohorts_rejects_non_positive(self) -> None:
        with self.assertRaises(ValueError):
            _scale_cohorts(DEVELOPER_COHORTS, 0)

    def test_builders_use_scaled_cohort_totals(self) -> None:
        scaled_devs = _scale_cohorts(DEVELOPER_COHORTS, 0.25)
        scaled_users = _scale_cohorts(USER_TESTER_COHORTS, 0.25)
        developers = _build_developer_agents(cycle=1, base_seed=7331, cohorts=scaled_devs)
        users = _build_user_tester_agents(cycle=1, base_seed=7331, cohorts=scaled_users)
        self.assertEqual(sum(count for _, count in scaled_devs), len(developers))
        self.assertEqual(sum(count for _, count in scaled_users), len(users))


if __name__ == "__main__":
    unittest.main()

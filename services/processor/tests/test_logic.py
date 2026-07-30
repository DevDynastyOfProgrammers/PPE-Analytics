import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logic import GeometryChecker, ViolationManager


class ViolationManagerTests(unittest.TestCase):
    def test_does_not_alert_before_minimum_duration(self):
        manager = ViolationManager()

        violation = manager.update_person(
            track_id=1,
            has_helmet=False,
            has_vest=False,
            current_time=0.0,
        )

        self.assertIsNone(violation)

    def test_alerts_when_ppe_is_missing_for_history_window(self):
        manager = ViolationManager()

        manager.update_person(
            track_id=1,
            has_helmet=False,
            has_vest=False,
            current_time=0.0,
        )
        violation = manager.update_person(
            track_id=1,
            has_helmet=False,
            has_vest=False,
            current_time=1.1,
        )

        self.assertEqual(violation, "no_helmet+no_vest")

    def test_suppresses_duplicate_alert_during_debounce_interval(self):
        manager = ViolationManager()

        manager.update_person(
            track_id=1,
            has_helmet=False,
            has_vest=False,
            current_time=0.0,
        )
        manager.update_person(
            track_id=1,
            has_helmet=False,
            has_vest=False,
            current_time=1.1,
        )
        violation = manager.update_person(
            track_id=1,
            has_helmet=False,
            has_vest=False,
            current_time=2.0,
        )

        self.assertIsNone(violation)


class GeometryCheckerTests(unittest.TestCase):
    def setUp(self):
        self.checker = GeometryChecker()
        self.zones = [
            {
                "id": 1,
                "name": "Test zone",
                "polygon_coordinates": [[0, 0], [100, 0], [100, 100], [0, 100]],
            }
        ]

    def test_returns_zone_for_person_with_feet_inside_polygon(self):
        result = self.checker.check_zones(
            person_box=[40, 20, 60, 80],
            zones=self.zones,
        )

        self.assertEqual(result, (True, "Test zone", 1))

    def test_returns_no_zone_for_person_with_feet_outside_polygon(self):
        result = self.checker.check_zones(
            person_box=[120, 20, 160, 80],
            zones=self.zones,
        )

        self.assertEqual(result, (False, None, None))


if __name__ == "__main__":
    unittest.main()
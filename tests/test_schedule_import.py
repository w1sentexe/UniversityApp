"""Регрессии разбора подгрупп из реальных выгрузок расписания."""

import unittest
from pathlib import Path

from tools.schedule_import.parser import parse_schedule


SOURCE = Path(__file__).parents[1] / "tools" / "schedule_import" / "files"


class ScheduleImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schedules, cls.reports = parse_schedule(SOURCE)

    def test_partial_cells_belong_only_to_their_subgroup(self) -> None:
        """УБ-41: в числителе занятия слева, в знаменателе справа."""
        schedule = self.schedules["УБ-41"]

        numerator = [
            (str(lesson.start_time), lesson.subgroups)
            for lesson in schedule.numerator.monday
            if lesson.name == "Сети и системы передачи инф."
        ]
        denominator = [
            (str(lesson.start_time), lesson.subgroups)
            for lesson in schedule.denominator.monday
            if lesson.name == "Сети и системы передачи инф."
        ]

        self.assertEqual(numerator, [("13:35:00", [1]), ("15:20:00", [1])])
        self.assertEqual(denominator, [("13:35:00", [2]), ("15:20:00", [2])])

    def test_service_markers_do_not_create_a_second_subgroup(self) -> None:
        teachers = [
            lesson.teacher_name
            for schedule in self.schedules.values()
            for week in (schedule.numerator, schedule.denominator)
            for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
            for lesson in getattr(week, day)
        ]

        self.assertNotIn("Z", teachers)


if __name__ == "__main__":
    unittest.main()

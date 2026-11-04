"""CampusPlanner 包。"""

from .core import (  # noqa: F401
    APP_NAME, APP_SUBTITLE, APP_VERSION, AppData, Course, CustomField, Exam,
    Period, Settings, WeekSpec, build_ics, current_week, data_path, date_of_week_day,
    default_term_name, expand_weeks, load_data, sample_data, save_data, weeks_label,
)

# tests/test_imports.py
"""Verify all module imports work correctly — catches missing deps and renamed files."""


class TestImports:
    def test_data_models(self):
        from data.models import Unit, _working_days_between

        assert Unit is not None
        assert _working_days_between is not None

    def test_data_db(self):
        from data.db import get_db, get_detailer_schedules, row_to_unit

        assert callable(get_db)
        assert callable(row_to_unit)
        assert callable(get_detailer_schedules)

    def test_data_loader(self):
        from data.loader import load_units, unit_fingerprint

        assert callable(load_units)
        assert callable(unit_fingerprint)

    def test_data_writer(self):
        from data.writer import save_unit

        assert callable(save_unit)

    def test_automation_import_csv(self):
        from automation.import_csv import import_csv, run_import

        assert callable(import_csv)
        assert callable(run_import)

    def test_automation_export_to_workbook(self):
        from automation.export_to_workbook import export_to_workbook

        assert callable(export_to_workbook)

    def test_automation_create_db(self):
        from automation.create_db import create_database

        assert callable(create_database)

    def test_gui_imports(self):
        """GUI imports require PyQt5 — verify it's importable."""
        from PyQt5.QtCore import QDate
        from PyQt5.QtWidgets import QApplication

        assert QApplication is not None
        assert QDate is not None

    def test_gui_list_panel(self):
        from gui.list_panel import ListPanel, UnitListModel

        assert callable(ListPanel)
        assert callable(UnitListModel)

    def test_main_import(self):
        import main

        assert hasattr(main, "main")

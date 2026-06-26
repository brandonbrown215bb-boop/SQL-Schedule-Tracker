# tests/test_workers.py
"""Tests for background QThread workers (SSRS, CSV, Excel operations)."""

from unittest.mock import MagicMock

from gui.main_window import CSVDiffWorker, CSVImportWorker, ExcelExportWorker, PullSSRSWorker


class TestBackgroundWorkers:
    def test_pull_ssrs_worker_success(self, qtbot):
        mock_import_service = MagicMock()
        mock_import_service.from_ssrs.return_value = "mock_ssrs_result"

        worker = PullSSRSWorker(
            import_service=mock_import_service,
            url="http://ssrs.example.com",
            lookback_days=15,
            lookahead_days=90,
        )

        received = []
        worker.finished.connect(lambda res: received.append(res))

        with qtbot.wait_signal(worker.finished, timeout=1000):
            worker.start()

        worker.wait()  # Ensure QThread is cleaned up

        assert len(received) == 1
        assert received[0] == "mock_ssrs_result"
        mock_import_service.from_ssrs.assert_called_once_with(
            url="http://ssrs.example.com",
            lookback_days=15,
            lookahead_days=90,
        )

    def test_pull_ssrs_worker_error(self, qtbot):
        mock_import_service = MagicMock()
        mock_import_service.from_ssrs.side_effect = Exception("SSRS Server Down")

        worker = PullSSRSWorker(
            import_service=mock_import_service,
            url="http://ssrs.example.com",
            lookback_days=15,
            lookahead_days=90,
        )

        errors = []
        worker.error.connect(lambda err: errors.append(err))

        with qtbot.wait_signal(worker.error, timeout=1000):
            worker.start()

        worker.wait()  # Ensure QThread is cleaned up

        assert len(errors) == 1
        assert "SSRS Server Down" in errors[0]

    def test_csv_diff_worker_success(self, qtbot):
        mock_import_service = MagicMock()
        mock_import_service.diff_before_import.return_value = "mock_diff"

        worker = CSVDiffWorker(import_service=mock_import_service, source_path="test.csv")

        received = []
        worker.finished.connect(lambda diff: received.append(diff))

        with qtbot.wait_signal(worker.finished, timeout=1000):
            worker.start()

        worker.wait()  # Ensure QThread is cleaned up

        assert len(received) == 1
        assert received[0] == "mock_diff"
        mock_import_service.diff_before_import.assert_called_once_with("test.csv")

    def test_csv_import_worker_success(self, qtbot):
        mock_import_service = MagicMock()
        mock_import_service.from_csv.return_value = "mock_import_result"

        worker = CSVImportWorker(import_service=mock_import_service, source_path="test.csv")

        received = []
        worker.finished.connect(lambda res: received.append(res))

        with qtbot.wait_signal(worker.finished, timeout=1000):
            worker.start()

        worker.wait()  # Ensure QThread is cleaned up

        assert len(received) == 1
        assert received[0] == "mock_import_result"
        mock_import_service.from_csv.assert_called_once_with("test.csv")

    def test_excel_export_worker_success(self, qtbot):
        mock_export_service = MagicMock()
        mock_export_service.to_excel.return_value = 142

        worker = ExcelExportWorker(
            export_service=mock_export_service, excel_path="out.xlsx", db_path="data.db"
        )

        received = []
        worker.finished.connect(lambda count: received.append(count))

        with qtbot.wait_signal(worker.finished, timeout=1000):
            worker.start()

        worker.wait()  # Ensure QThread is cleaned up

        assert len(received) == 1
        assert received[0] == 142
        mock_export_service.to_excel.assert_called_once_with("out.xlsx", "data.db")

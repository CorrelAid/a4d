"""Unit tests for patient extraction helper functions."""

import random
from unittest.mock import Mock

import pytest
from openpyxl import Workbook

from a4d.extract.patient import (
    filter_valid_columns,
    find_data_start_row,
    find_dropped_data_columns,
    find_layout_changes,
    merge_headers,
    read_header_rows,
    read_patient_rows,
    recover_blank_headers,
)


def create_mock_mapper(known_columns: set[str]):
    """Create a mock ColumnMapper that validates specific column names."""
    mapper = Mock()
    mapper.is_known_column = lambda col: col in known_columns
    return mapper


class TestFindDataStartRow:
    """Tests for find_data_start_row() function."""

    def test_data_starts_at_row_1(self):
        """Test when data starts at the very first row."""
        wb = Workbook()
        ws = wb.active
        ws["A1"] = 1
        ws["A2"] = 2

        result = find_data_start_row(ws)
        assert result == 1

        wb.close()

    def test_data_starts_after_empty_rows(self):
        """Test when there are empty rows before data."""
        wb = Workbook()
        ws = wb.active
        # Leave rows 1-10 empty
        ws["A11"] = 1
        ws["A12"] = 2

        result = find_data_start_row(ws)
        assert result == 11

        wb.close()

    def test_realistic_tracker_layout(self):
        """Test with realistic tracker layout (headers at rows 75-76, data at 77)."""
        wb = Workbook()
        ws = wb.active

        # Simulate typical tracker: empty rows, then title rows, then headers, then data
        # Title area NOT in column A (column A stays empty until headers)
        ws["B1"] = "Hospital Name"
        ws["C1"] = "General Hospital"

        # Headers at rows 75-76 (typical for real trackers)
        ws["B75"] = "Patient"
        ws["B76"] = "ID*"

        # Data starts at row 77
        ws["A77"] = 1
        ws["A78"] = 2

        result = find_data_start_row(ws)
        assert result == 77  # First non-None in column A

        wb.close()

    def test_randomized_data_position(self):
        """Test with randomized data start position."""
        wb = Workbook()
        ws = wb.active

        # Random start position between 10 and 100
        random_start = random.randint(10, 100)

        # Insert first data value at random position (must be numeric)
        ws[f"A{random_start}"] = 1

        result = find_data_start_row(ws)
        assert result == random_start

        wb.close()

    def test_column_a_empty_raises_error(self):
        """Test that ValueError is raised when column A is empty."""
        wb = Workbook()
        ws = wb.active

        # Put data in other columns but not A
        ws["B1"] = "Some data"
        ws["C5"] = "More data"

        with pytest.raises(ValueError, match="No patient data found in column A"):
            find_data_start_row(ws)

        wb.close()

    def test_ignores_none_values(self):
        """Test that None/empty cells are skipped correctly."""
        wb = Workbook()
        ws = wb.active

        # Explicitly set some cells to None (they start as None anyway)
        ws["A1"] = None
        ws["A2"] = None
        ws["A3"] = None
        ws["A4"] = 1  # First numeric data

        result = find_data_start_row(ws)
        assert result == 4

        wb.close()

    def test_scans_read_only_worksheet_in_one_pass(self, tmp_path):
        """Must not re-parse the sheet's XML on every row (O(n^2) on read-only sheets).

        ReadOnlyWorksheet.cell() re-parses from row 1 on every call, so a
        per-row .cell() loop is quadratic in the row count before data starts.
        Asserts _cells_by_row (the underlying XML scan) runs at most once,
        which only a single iter_rows() pass over column A can achieve.
        """
        from unittest.mock import patch

        from openpyxl import Workbook, load_workbook
        from openpyxl.worksheet._read_only import ReadOnlyWorksheet

        path = tmp_path / "dense.xlsx"
        wb = Workbook()
        ws = wb.active
        for row in range(1, 200):
            for col in range(1, 40):
                ws.cell(row, col, value=f"text{row}_{col}")
        ws["A200"] = 1
        wb.save(path)
        wb.close()

        wb2 = load_workbook(path, read_only=True)
        ws2 = wb2.active

        with patch.object(ReadOnlyWorksheet, "_cells_by_row", wraps=ws2._cells_by_row) as spy:
            result = find_data_start_row(ws2)

        assert result == 200
        assert spy.call_count == 1

        wb2.close()


class TestReadPatientRows:
    """Tests for read_patient_rows() row-acceptance rules."""

    @staticmethod
    def _sheet(rows):
        wb = Workbook()
        ws = wb.active
        for r, values in enumerate(rows, start=1):
            for c, value in enumerate(values, start=1):
                if value is not None:
                    ws.cell(row=r, column=c, value=value)
        return wb, ws

    def test_keeps_a_numbered_row(self):
        wb, ws = self._sheet([[1, "VN_VC001", "VN_VC001", "Y"]])

        assert len(read_patient_rows(ws, 1, 4)) == 1

        wb.close()

    def test_keeps_an_unnumbered_row_that_carries_data(self):
        """2024_Mahosot Jun24 row 380: a real patient record whose row number
        was never filled in. R drops it -- its data block is the span of the
        row-number column alone -- so Python keeping it is a deliberate
        divergence, not an accident."""
        wb, ws = self._sheet([[None, "LA-MH088", "LA-MH088", "Y", "2024-06-19"]])

        assert len(read_patient_rows(ws, 1, 5)) == 1

        wb.close()

    def test_drops_an_unnumbered_row_that_only_repeats_its_own_identifier(self):
        """2024_Vietnam National Children Jul24 rows 165-188: a bare list of
        patient IDs left below the data block, two non-empty cells per row and
        nothing else. Treating those as monthly records invented 24 patients."""
        wb, ws = self._sheet([[None, "VN_VC052", "VN_VC052", None, None]])

        assert read_patient_rows(ws, 1, 5) == []

        wb.close()

    def test_stops_at_the_first_completely_empty_row(self):
        wb, ws = self._sheet(
            [[1, "VN_VC001", "VN_VC001"], [None, None, None], [2, "VN_VC002", "VN_VC002"]]
        )

        assert len(read_patient_rows(ws, 1, 3)) == 1

        wb.close()

    def test_skips_a_row_with_neither_number_nor_identifier(self):
        wb, ws = self._sheet([[None, None, "stray note"], [1, "VN_VC001", "VN_VC001"]])

        rows = read_patient_rows(ws, 1, 3)

        assert [r[1] for r in rows] == ["VN_VC001"]

        wb.close()


class TestReadHeaderRows:
    """Tests for read_header_rows() function."""

    def test_basic_two_row_headers(self):
        """Test reading basic two-row headers."""
        wb = Workbook()
        ws = wb.active

        # Data starts at row 5, so headers are at rows 3 and 4
        ws["A3"] = "Patient"
        ws["B3"] = "Date"
        ws["C3"] = "HbA1c"

        ws["A4"] = "ID*"
        ws["B4"] = "(dd-mmm-yyyy)"
        ws["C4"] = "%"

        ws["A5"] = "P001"  # Data starts here

        header_1, header_2 = read_header_rows(ws, data_start_row=5)

        assert header_1 == ["ID*", "(dd-mmm-yyyy)", "%"]
        assert header_2 == ["Patient", "Date", "HbA1c"]

        wb.close()

    def test_trims_to_last_non_none_column(self):
        """Test that headers are trimmed to last non-None column."""
        wb = Workbook()
        ws = wb.active

        # Data starts at row 10
        ws["A8"] = "Patient"
        ws["B8"] = "Name"
        ws["C8"] = "Age"
        # D8-Z8 remain None

        ws["A9"] = "ID*"
        ws["B9"] = None
        ws["C9"] = None

        ws["A10"] = "P001"

        header_1, header_2 = read_header_rows(ws, data_start_row=10)

        # Should trim to column C (last non-None)
        assert len(header_1) == 3
        assert len(header_2) == 3
        assert header_1 == ["ID*", None, None]
        assert header_2 == ["Patient", "Name", "Age"]

        wb.close()

    def test_realistic_tracker_width(self):
        """Test with realistic tracker dimensions (31 columns)."""
        wb = Workbook()
        ws = wb.active

        data_start_row = 77

        # Create 31 columns of headers
        for col_idx in range(1, 32):  # 1 to 31 inclusive
            ws.cell(row=75, column=col_idx, value=f"H2_Col{col_idx}")
            ws.cell(row=76, column=col_idx, value=f"H1_Col{col_idx}")

        # Put data at row 77
        ws.cell(row=77, column=1, value="P001")

        header_1, header_2 = read_header_rows(ws, data_start_row=data_start_row)

        assert len(header_1) == 31
        assert len(header_2) == 31
        assert header_1[0] == "H1_Col1"
        assert header_1[30] == "H1_Col31"
        assert header_2[0] == "H2_Col1"
        assert header_2[30] == "H2_Col31"

        wb.close()

    def test_mixed_none_values_in_headers(self):
        """Test headers with mixed None and non-None values."""
        wb = Workbook()
        ws = wb.active

        # Header row 2 (further from data)
        ws["A3"] = "Patient"
        ws["B3"] = None
        ws["C3"] = "Updated HbA1c"
        ws["D3"] = None  # Horizontally merged
        ws["E3"] = None

        # Header row 1 (closer to data)
        ws["A4"] = "ID*"
        ws["B4"] = "Name"
        ws["C4"] = "%"
        ws["D4"] = "(dd-mmm-yyyy)"
        ws["E4"] = None

        ws["A5"] = "P001"  # Data

        header_1, header_2 = read_header_rows(ws, data_start_row=5)

        # Should trim to column D (last non-None in header_1)
        assert len(header_1) == 4
        assert len(header_2) == 4
        assert header_1 == ["ID*", "Name", "%", "(dd-mmm-yyyy)"]
        assert header_2 == ["Patient", None, "Updated HbA1c", None]

        wb.close()

    def test_randomized_header_position(self):
        """Test with randomized data start position."""
        wb = Workbook()
        ws = wb.active

        # Random data start between rows 20 and 100
        random_data_start = random.randint(20, 100)
        header_row_1 = random_data_start - 1
        header_row_2 = random_data_start - 2

        # Set headers
        ws.cell(row=header_row_2, column=1, value="Header2")
        ws.cell(row=header_row_1, column=1, value="Header1")
        ws.cell(row=random_data_start, column=1, value="Data")

        header_1, header_2 = read_header_rows(ws, data_start_row=random_data_start)

        assert header_1 == ["Header1"]
        assert header_2 == ["Header2"]

        wb.close()

    def test_respects_max_cols_parameter(self):
        """Test that max_cols parameter limits the read width."""
        wb = Workbook()
        ws = wb.active

        # Create 200 columns of data
        for col_idx in range(1, 201):
            ws.cell(row=3, column=col_idx, value=f"H2_{col_idx}")
            ws.cell(row=4, column=col_idx, value=f"H1_{col_idx}")

        ws["A5"] = "Data"

        # Read with max_cols=50
        header_1, header_2 = read_header_rows(ws, data_start_row=5, max_cols=50)

        # Should only read up to column 50
        assert len(header_1) == 50
        assert len(header_2) == 50
        assert header_1[49] == "H1_50"

        wb.close()

    def test_all_none_headers(self):
        """Test when both header rows are completely None.

        Note: When no non-None values are found, the function returns
        max_cols None values (default behavior). In practice, this edge
        case doesn't occur as real trackers always have headers.
        """
        wb = Workbook()
        ws = wb.active

        # Headers are all None
        # (openpyxl cells are None by default)

        ws["A5"] = "Data"

        header_1, header_2 = read_header_rows(ws, data_start_row=5, max_cols=10)

        # Returns max_cols None values when nothing is found
        assert len(header_1) == 10
        assert len(header_2) == 10
        assert all(h is None for h in header_1)
        assert all(h is None for h in header_2)

        wb.close()


class TestMergeHeaders:
    """Tests for merge_headers() function."""

    def test_both_headers_present(self):
        """Test merging when both header rows have values."""
        h1 = ["%", "mmol/L", "kg"]
        h2 = ["HbA1c", "FBG", "Weight"]
        result = merge_headers(h1, h2)
        assert result == ["HbA1c %", "FBG mmol/L", "Weight kg"]

    def test_only_h2_present(self):
        """Test when only header row 2 has values."""
        h1 = [None, None, None]
        h2 = ["Patient ID", "Name", "Age"]
        result = merge_headers(h1, h2)
        assert result == ["Patient ID", "Name", "Age"]

    def test_only_h1_present(self):
        """Test when only header row 1 has values (single-line headers)."""
        h1 = ["Patient ID", "Name", "Age"]
        h2 = [None, None, None]
        result = merge_headers(h1, h2)
        assert result == ["Patient ID", "Name", "Age"]

    def test_horizontal_merge_forward_fill(self):
        """Test forward-fill with synonym validation.

        Forward-fill happens when mapper validates the combined header.
        """
        h1 = ["%", "(dd-mmm-yyyy)", "mmol/L", "(dd-mmm-yyyy)"]
        h2 = ["Updated HbA1c", None, "Updated FBG", None]
        # Mock mapper that knows these forward-filled patterns
        mapper = create_mock_mapper(
            {
                "Updated HbA1c %",
                "Updated HbA1c (dd-mmm-yyyy)",
                "Updated FBG mmol/L",
                "Updated FBG (dd-mmm-yyyy)",
            }
        )
        result = merge_headers(h1, h2, mapper)
        assert result == [
            "Updated HbA1c %",
            "Updated HbA1c (dd-mmm-yyyy)",
            "Updated FBG mmol/L",
            "Updated FBG (dd-mmm-yyyy)",
        ]

    def test_mixed_headers(self):
        """Test realistic mix of header patterns.

        Forward-fill happens when mapper validates the combined header.
        """
        h1 = ["ID*", "Name", "%", "(date)", None, "kg"]
        h2 = ["Patient", None, "HbA1c", None, "Notes", "Weight"]
        # Mock mapper that validates these forward-fills
        mapper = create_mock_mapper(
            {
                "Patient ID*",
                "Patient Name",
                "HbA1c %",
                "HbA1c (date)",
            }
        )
        result = merge_headers(h1, h2, mapper)
        assert result == [
            "Patient ID*",
            "Patient Name",  # Forward-filled and validated
            "HbA1c %",
            "HbA1c (date)",  # Forward-filled and validated
            "Notes",
            "Weight kg",
        ]

    def test_none_values_reset_forward_fill(self):
        """Test that None in both headers results in None.

        Forward-fill only happens when h1 exists and mapper validates.
        """
        h1 = ["%", "(date)", None, "kg"]
        h2 = ["HbA1c", None, None, "Weight"]
        # Mock mapper that validates HbA1c forward-fills
        mapper = create_mock_mapper(
            {
                "HbA1c %",
                "HbA1c (date)",
            }
        )
        result = merge_headers(h1, h2, mapper)
        assert result == [
            "HbA1c %",
            "HbA1c (date)",
            None,
            "Weight kg",
        ]

    def test_whitespace_normalization(self):
        """Test that extra whitespace and newlines are normalized."""
        h1 = ["ID\n(format)", "  Name  "]
        h2 = ["Patient\nID", "Full  Name"]
        result = merge_headers(h1, h2)
        assert result == [
            "Patient ID ID (format)",
            "Full Name Name",
        ]

    def test_updated_year_marker_inherits_previous_subject(self):
        """The 2022 template labels an update-date column "Updated 2022".

        The subject it belongs to is only in the column to its left, so
        "Updated <year>" alone must not become the column name. Mirrors R's
        script1_helper_read_patient_data.R fixup, which rewrites the same cell.
        """
        h1 = ["mm HG", "Date"]
        h2 = ["Blood Pressure ", "Updated\n2022"]
        result = merge_headers(h1, h2)
        assert result == ["Blood Pressure mm HG", "Blood Pressure Date"]

    def test_updated_year_marker_on_patient_list(self):
        """Same marker, different subject: the Patient List's education column."""
        h1 = [None, "Date"]
        h2 = ["Level of Education\nOr Occupation", " Updated \n2022"]
        result = merge_headers(h1, h2)
        assert result == [
            "Level of Education Or Occupation",
            "Level of Education Or Occupation Date",
        ]

    def test_updated_year_marker_without_previous_subject(self):
        """With nothing to inherit, the marker is left alone rather than dropped."""
        h1 = ["Date"]
        h2 = ["Updated 2022"]
        result = merge_headers(h1, h2)
        assert result == ["Updated 2022 Date"]

    def test_updated_without_year_is_not_a_marker(self):
        """ "Updated HbA1c" is a real subject, not a continuation marker."""
        h1 = ["%"]
        h2 = ["Updated HbA1c"]
        result = merge_headers(h1, h2)
        assert result == ["Updated HbA1c %"]

    def test_empty_headers(self):
        """Test with empty header lists."""
        result = merge_headers([], [])
        assert result == []

    def test_single_column(self):
        """Test with single column."""
        h1 = ["ID"]
        h2 = ["Patient"]
        result = merge_headers(h1, h2)
        assert result == ["Patient ID"]


class TestFilterValidColumns:
    """Tests for filter_valid_columns() function."""

    def test_all_valid_headers(self):
        """Test when all headers are valid (no None)."""
        headers = ["ID", "Name", "Age"]
        data = [("1", "Alice", "30"), ("2", "Bob", "25")]
        valid_headers, filtered_data = filter_valid_columns(headers, data)

        assert valid_headers == ["ID", "Name", "Age"]
        assert filtered_data == [["1", "Alice", "30"], ["2", "Bob", "25"]]

    def test_some_none_headers(self):
        """Test filtering out None headers."""
        headers = ["ID", None, "Name", None, "Age"]
        data = [("1", "x", "Alice", "y", "30"), ("2", "x", "Bob", "y", "25")]
        valid_headers, filtered_data = filter_valid_columns(headers, data)

        assert valid_headers == ["ID", "Name", "Age"]
        assert filtered_data == [["1", "Alice", "30"], ["2", "Bob", "25"]]

    def test_all_none_headers(self):
        """Test when all headers are None."""
        headers = [None, None, None]
        data = [("1", "2", "3"), ("4", "5", "6")]
        valid_headers, filtered_data = filter_valid_columns(headers, data)

        assert valid_headers == []
        assert filtered_data == []

    def test_empty_data(self):
        """Test with empty data."""
        headers = ["ID", "Name"]
        data = []
        valid_headers, filtered_data = filter_valid_columns(headers, data)

        assert valid_headers == ["ID", "Name"]
        assert filtered_data == []

    def test_single_valid_column(self):
        """Test with single valid column."""
        headers = [None, "ID", None]
        data = [("x", "1", "y"), ("x", "2", "y")]
        valid_headers, filtered_data = filter_valid_columns(headers, data)

        assert valid_headers == ["ID"]
        assert filtered_data == [["1"], ["2"]]

    def test_preserves_order(self):
        """Test that column order is preserved."""
        headers = ["A", None, "B", None, "C", "D", None]
        data = [(1, 2, 3, 4, 5, 6, 7)]
        valid_headers, filtered_data = filter_valid_columns(headers, data)

        assert valid_headers == ["A", "B", "C", "D"]
        assert filtered_data == [[1, 3, 5, 6]]


class TestFindDroppedDataColumns:
    """Tests for find_dropped_data_columns() function."""

    def test_reports_headerless_column_holding_text(self):
        headers = ["ID", None, "Age"]
        data = [("1", "Self-mixed BD", "30"), ("2", "Basal-Bolus", "25")]

        assert find_dropped_data_columns(headers, data) == [(1, 2)]

    def test_ignores_headerless_column_that_is_empty(self):
        headers = ["ID", None, "Age"]
        data = [("1", None, "30"), ("2", "", "25")]

        assert find_dropped_data_columns(headers, data) == []

    def test_ignores_row_counter(self):
        """A headerless all-numeric column is the tracker's own row counter."""
        headers = [None, "ID"]
        data = [("1", "KH_PK001"), ("2", "KH_PK002"), ("3.0", "KH_PK003")]

        assert find_dropped_data_columns(headers, data) == []

    def test_reports_mixed_numeric_and_text_column(self):
        """A stray number among real text does not make the column a counter."""
        headers = [None, "ID"]
        data = [("7", "KH_JV001"), ("*Needs Meter", "KH_JV002")]

        assert find_dropped_data_columns(headers, data) == [(0, 2)]

    def test_ignores_columns_that_have_headers(self):
        headers = ["ID", "Notes"]
        data = [("1", "text")]

        assert find_dropped_data_columns(headers, data) == []


class TestRecoverBlankHeaders:
    """Tests for recover_blank_headers() function."""

    def test_recovers_from_the_one_sibling_that_names_the_column(self):
        headers = ["ID", None]
        data = [("1", "Self-mixed BD")]
        siblings = [["ID", "Insulin Regime"]]

        assert recover_blank_headers(headers, data, siblings) == ["ID", "Insulin Regime"]

    def test_abstains_when_siblings_disagree(self):
        """Two candidate names is a guess, not a recovery."""
        headers = ["ID", None]
        data = [("1", "x")]
        siblings = [["ID", "Complication Screening"], ["ID", "Hospitalisation Date"]]

        assert recover_blank_headers(headers, data, siblings) == ["ID", None]

    def test_agreeing_siblings_are_not_a_disagreement(self):
        headers = ["ID", None]
        data = [("1", "x")]
        siblings = [["ID", "Clinic Visit"], ["ID", "Clinic Visit"], ["ID", None]]

        assert recover_blank_headers(headers, data, siblings) == ["ID", "Clinic Visit"]

    def test_abstains_when_no_sibling_names_the_column(self):
        """The 2022 template's hidden merged-cell column is blank in every sheet."""
        headers = ["ID", None]
        data = [("1", "Self-mixed BD")]
        siblings = [["ID", None], ["ID", None]]

        assert recover_blank_headers(headers, data, siblings) == ["ID", None]

    def test_leaves_an_empty_column_alone(self):
        """A blank header over no data is a spacer, not a lost column."""
        headers = ["ID", None]
        data = [("1", None)]
        siblings = [["ID", "Insulin Regime"]]

        assert recover_blank_headers(headers, data, siblings) == ["ID", None]

    def test_ignores_the_row_counter(self):
        headers = [None, "ID"]
        data = [("1", "KH_PK001"), ("2", "KH_PK002")]
        siblings = [["Nr", "ID"]]

        assert recover_blank_headers(headers, data, siblings) == [None, "ID"]

    def test_never_creates_a_duplicate_column_name(self):
        """A donor name this sheet already uses would collide on rename."""
        headers = ["ID", "Insulin Regime", None]
        data = [("1", "a", "b")]
        siblings = [["ID", "Insulin Regime", "Insulin Regime"]]

        assert recover_blank_headers(headers, data, siblings) == ["ID", "Insulin Regime", None]

    def test_tolerates_siblings_of_different_width(self):
        headers = ["ID", None]
        data = [("1", "x")]
        siblings = [["ID"], ["ID", "Clinic Visit"]]

        assert recover_blank_headers(headers, data, siblings) == ["ID", "Clinic Visit"]

    def test_no_siblings_is_a_no_op(self):
        headers = ["ID", None]
        data = [("1", "x")]

        assert recover_blank_headers(headers, data, []) == ["ID", None]


class TestFindLayoutChanges:
    """Tests for find_layout_changes() function."""

    def test_flags_a_position_whose_canonical_column_changes(self):
        layouts = {
            "Jan20": ["Patient ID", "Baseline FBG (mmol/dL)"],
            "Jun20": ["Patient ID", "Baseline FBG (mg/dL)"],
        }
        mapper = create_mock_mapper(set())
        mapper.get_standard_name = lambda h: {
            "Baseline FBG (mmol/dL)": "fbg_baseline_mmol",
            "Baseline FBG (mg/dL)": "fbg_baseline_mg",
        }.get(h, h)

        changes = find_layout_changes(layouts, mapper)

        assert len(changes) == 1
        assert changes[0].index == 1
        assert changes[0].renames_only is False
        assert changes[0].headers == ["Baseline FBG (mg/dL)", "Baseline FBG (mmol/dL)"]

    def test_a_pure_rename_is_flagged_but_marked_harmless(self):
        layouts = {
            "Jan20": ["Patient ID", "Insulin regime"],
            "Mar20": ["Patient ID", "Insulin regimen"],
        }
        mapper = create_mock_mapper(set())
        mapper.get_standard_name = lambda h: "insulin_regimen" if "nsulin" in h else h

        changes = find_layout_changes(layouts, mapper)

        assert len(changes) == 1
        assert changes[0].renames_only is True

    def test_sheets_that_agree_produce_nothing(self):
        layouts = {"Jan20": ["Patient ID", "Age"], "Feb20": ["Patient ID", "Age"]}
        mapper = create_mock_mapper(set())
        mapper.get_standard_name = lambda h: h

        assert find_layout_changes(layouts, mapper) == []

    def test_a_blank_header_is_not_a_change(self):
        """One sheet leaving a header empty is recover_blank_headers' business."""
        layouts = {"Jan20": ["Patient ID", "Age"], "Feb20": ["Patient ID", None]}
        mapper = create_mock_mapper(set())
        mapper.get_standard_name = lambda h: h

        assert find_layout_changes(layouts, mapper) == []

    def test_a_single_sheet_cannot_disagree_with_itself(self):
        mapper = create_mock_mapper(set())
        mapper.get_standard_name = lambda h: h

        assert find_layout_changes({"Jan20": ["Patient ID"]}, mapper) == []

    def test_sheets_of_different_width_are_compared_where_they_overlap(self):
        layouts = {"Jan20": ["ID", "Insulin Regimen", "BASAL"], "Apr20": ["ID", "BASAL"]}
        mapper = create_mock_mapper(set())
        mapper.get_standard_name = lambda h: h

        changes = find_layout_changes(layouts, mapper)

        assert [c.index for c in changes] == [1]

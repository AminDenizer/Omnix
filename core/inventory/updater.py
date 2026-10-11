"""
Omnix Core - Stock Policy Threshold Updater
Governing Document: Phase 1 Refinement Specification

Safely updates literal Min Stock and Target Stock threshold cells in the
explicitly named 'Stock Policy' worksheet of the Inventory workbook (Inventory.xlsm).
Uses native Microsoft Excel automation through COM (pywin32) on Windows to ensure 100%
preservation of VBA macros, Excel Data Validation extensions (<extLst>), formulas,
calculated columns, formatting, and workbook integrity.
"""

import os
from typing import Tuple, Optional, Any, Callable

from core.inventory.models import build_group_key, normalize_package
from core.inventory.loader import resolve_inventory_database_path


class StockPolicyUpdateError(Exception):
    """Raised when updating Stock Policy thresholds fails."""
    pass


class WorkbookLockedError(StockPolicyUpdateError):
    """Raised when the workbook is opened or locked by another process."""
    pass


class StockPolicyWriter:
    """
    Safely writes Min Stock and Target Stock threshold values to the 'Stock Policy' worksheet.
    Identifies the exact policy row by canonical Group Key.
    """

    def __init__(self, com_dispatch_fn: Optional[Callable[..., Any]] = None):
        """
        Args:
            com_dispatch_fn: Optional factory for Excel application (used for testing/mocking).
        """
        self._com_dispatch_fn = com_dispatch_fn

    def update_policy(
        self,
        workbook_path: str,
        group_key: str,
        min_stock: int,
        target_stock: int,
    ) -> Tuple[bool, str]:
        """
        Updates Min Stock and Target Stock for the specified policy group in the workbook.

        Validation rules:
        - min_stock and target_stock must be non-negative integers.
        - target_stock >= min_stock >= 0.

        Returns:
            Tuple of (success: bool, message: str)
        """
        # 1. Parameter Validation
        if not isinstance(min_stock, (int, float)) or not isinstance(target_stock, (int, float)):
            return False, "Min Stock and Target Stock must be numeric values."

        min_val = int(round(min_stock))
        tgt_val = int(round(target_stock))

        if min_val < 0 or tgt_val < 0:
            return False, "Threshold values must be non-negative integers (>= 0)."

        if tgt_val < min_val:
            return False, (
                f"Target Stock ({tgt_val}) cannot be less than Min Stock ({min_val}). "
                "Target Stock must be greater than or equal to Min Stock."
            )

        # 2. File Path Resolution & Accessibility
        try:
            resolved_path = resolve_inventory_database_path(workbook_path)
        except Exception as e:
            return False, f"Could not resolve inventory workbook path: {e}"

        if not os.path.exists(resolved_path):
            return False, f"Inventory workbook not found at: {resolved_path}"

        if not os.access(resolved_path, os.W_OK):
            return False, (
                f"The workbook file '{os.path.basename(resolved_path)}' is marked read-only on disk. "
                "Please check file permissions."
            )

        # 3. Check for Excel COM support
        try:
            import win32com.client
        except ImportError:
            return False, (
                "Native Excel COM automation (pywin32) is not installed. "
                "Cannot safely write to .xlsm workbook without risking feature corruption."
            )

        # 4. Perform Update via Excel COM
        abs_path = os.path.abspath(resolved_path)
        excel = None
        wb = None
        ws = None
        has_co_init = False
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
                has_co_init = True
            except Exception:
                pass

            if self._com_dispatch_fn:
                excel = self._com_dispatch_fn("Excel.Application")
            else:
                excel = win32com.client.DispatchEx("Excel.Application")

            excel.Visible = False
            excel.DisplayAlerts = False

            try:
                wb = excel.Workbooks.Open(abs_path, ReadOnly=False)
            except Exception as e:
                err_msg = str(e)
                return False, (
                    f"Failed to open '{os.path.basename(abs_path)}' in Excel. "
                    f"The file may be exclusively locked by another process or application.\nDetails: {err_msg}"
                )

            if getattr(wb, "ReadOnly", False):
                return False, (
                    f"The workbook '{os.path.basename(abs_path)}' is currently open in read-only mode "
                    "or locked by another Excel session. Please close the file in Excel and try again."
                )

            # Access 'Stock Policy' worksheet
            for sheet in wb.Worksheets:
                if sheet.Name == "Stock Policy":
                    ws = sheet
                    break

            if ws is None:
                return False, "Worksheet 'Stock Policy' not found in workbook."

            # Find Column Indices in Row 1
            min_col: Optional[int] = None
            target_col: Optional[int] = None
            key_col: Optional[int] = None

            col_limit = 25
            for col in range(1, col_limit + 1):
                val = ws.Cells(1, col).Value
                if val:
                    val_str = str(val).strip().lower()
                    if "min stock" in val_str or val_str == "min_stock":
                        min_col = col
                    elif "target stock" in val_str or val_str == "target_stock":
                        target_col = col
                    elif "group key" in val_str:
                        key_col = col

            if min_col is None:
                min_col = 7
            if target_col is None:
                target_col = 8
            if key_col is None:
                key_col = 10

            # Scan rows to locate the exact policy row by Group Key
            target_row: Optional[int] = None
            row = 2
            consecutive_empty = 0

            while consecutive_empty < 5 and row < 500:
                row_key = None
                if key_col is not None:
                    cell_val = ws.Cells(row, key_col).Value
                    if cell_val:
                        row_key = str(cell_val).strip()

                if not row_key:
                    c1 = ws.Cells(row, 1).Value
                    c2 = ws.Cells(row, 2).Value
                    c3 = ws.Cells(row, 3).Value
                    c4 = ws.Cells(row, 4).Value
                    c5 = ws.Cells(row, 5).Value
                    if c1 or c2 or c3 or c4 or c5:
                        row_key = build_group_key(
                            str(c1 or ""),
                            str(c2 or ""),
                            str(c3 or ""),
                            normalize_package(c4),
                            str(c5 or ""),
                        )

                if row_key:
                    consecutive_empty = 0
                    if row_key == group_key:
                        target_row = row
                        break
                else:
                    consecutive_empty += 1

                row += 1

            if target_row is None:
                return False, f"Policy group '{group_key}' was not found in 'Stock Policy' worksheet."

            # Update the two literal cells only
            ws.Cells(target_row, min_col).Value = min_val
            ws.Cells(target_row, target_col).Value = tgt_val

            # Save
            wb.Save()
            return True, f"Successfully updated Min Stock ({min_val}) and Target Stock ({tgt_val}) for [{group_key}]."

        except Exception as e:
            return False, f"Unexpected error while writing to Excel workbook via COM: {e}"

        finally:
            ws = None
            if wb is not None:
                try:
                    wb.Close(SaveChanges=False)
                except Exception:
                    pass
                wb = None
            if excel is not None:
                try:
                    excel.Quit()
                except Exception:
                    pass
                excel = None
            import gc
            gc.collect()
            if has_co_init:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

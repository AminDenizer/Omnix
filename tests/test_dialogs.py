import pytest
from PyQt6.QtWidgets import QDialog
from models import Component
from database import Database
from ui.component_dialog import ComponentDialog
from ui.bulk_stock_dialog import BulkStockDialog
from ui.drawer_view import DrawerViewDialog
from ui.category_settings_dialog import CategorySettingsDialog


class TestDialogs:
    """Test suite for Omnix dialog forms and modals."""

    def test_component_dialog_add_mode(self, qapp, temp_db):
        dlg = ComponentDialog(db=temp_db)
        assert dlg is not None
        assert "ثبت قطعه جدید" in dlg.windowTitle()
        
        # Fill in form fields
        dlg.name_input.setText("مقاومت آجری")
        dlg.value_input.setText("5W 10R")
        dlg.qty_spin.setValue(20)
        dlg.drawers_input.setText("3:20")
        
        comp = dlg.get_component_data()
        assert comp.name == "مقاومت آجری"
        assert comp.value == "5W 10R"
        assert comp.quantity == 20
        assert comp.drawers == "3:20"
        dlg.close()

    def test_component_dialog_edit_mode(self, qapp, temp_db, sample_component):
        comp_id = temp_db.add_component(sample_component)
        comp = temp_db.get_component(comp_id)

        dlg = ComponentDialog(component=comp, db=temp_db)
        assert "ویرایش" in dlg.windowTitle()
        assert dlg.value_input.text() == comp.value
        assert dlg.qty_spin.value() == comp.quantity
        dlg.close()

    def test_bulk_stock_dialog(self, qapp, sample_component):
        dlg = BulkStockDialog(component=sample_component)
        assert dlg is not None
        assert "موجودی" in dlg.windowTitle()
        assert len(dlg.drawer_spinboxes) == len(sample_component.drawer_list)
        
        # Test spinbox manipulation
        first_drawer = sample_component.drawer_list[0]
        dlg.drawer_spinboxes[first_drawer].setValue(10)
        
        is_deduct, total_amount, breakdown = dlg.get_result()
        assert breakdown[first_drawer] == 10
        assert is_deduct is False
        assert total_amount == dlg.total_amount_spin.value()
        dlg.close()

    def test_drawer_view_dialog(self, qapp, sample_db_with_data):
        dlg = DrawerViewDialog(db=sample_db_with_data)
        assert dlg is not None
        assert "بازرسی" in dlg.windowTitle()
        assert dlg.drawer_combo.count() >= 1
        dlg.close()

    def test_category_settings_dialog(self, qapp, temp_db):
        dlg = CategorySettingsDialog(db=temp_db)
        assert dlg is not None
        assert "تنظیمات" in dlg.windowTitle()
        
        # Add custom category through dialog
        dlg.new_cat_input.setText("Wireless Modules")
        dlg._add_custom_category()
        assert "Wireless Modules" in temp_db.get_custom_categories()
        dlg.close()

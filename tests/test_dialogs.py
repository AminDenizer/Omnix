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
        
        # Test spinbox manipulation and bidirectional sync
        first_drawer = sample_component.drawer_list[0]
        dlg.drawer_spinboxes[first_drawer].setValue(10)
        
        is_deduct, total_amount, breakdown = dlg.get_result()
        assert breakdown[first_drawer] == 10
        assert is_deduct is False
        assert total_amount == dlg.total_amount_spin.value()
        
        # Test deduct mode with 100 and 150 units
        five_drawer_comp = Component(
            id=99,
            name="پتانسیومتر مولتی‌ترن",
            value="3296W-103 (10k)",
            package="Through-Hole (DIP)",
            category="Resistor",
            quantity=250,
            min_alert=40,
            drawers="1:100, 2:80, 5:50, 8:20, 11:0",
            description=""
        )
        deduct_dlg = BulkStockDialog(component=five_drawer_comp)
        deduct_dlg.radio_deduct.setChecked(True)
        assert deduct_dlg.btn_auto_distribute.isVisible() is False
        
        deduct_dlg.total_amount_spin.setValue(100)
        assert deduct_dlg.btn_submit.isEnabled() is True
        
        is_ded, total_amt, bdown = deduct_dlg.get_result()
        assert is_ded is True
        assert total_amt == 100
        assert bdown[1] == 100
        
        # Test deducting 150 with fair distribution across drawers
        deduct_dlg.total_amount_spin.setValue(150)
        deduct_dlg.btn_equal_distribute.click()
        assert deduct_dlg.drawer_spinboxes[1].value() == 44
        assert deduct_dlg.drawer_spinboxes[2].value() == 43
        assert deduct_dlg.drawer_spinboxes[5].value() == 43
        assert deduct_dlg.drawer_spinboxes[8].value() == 20
        assert deduct_dlg.drawer_spinboxes[11].value() == 0
        assert sum(s.value() for s in deduct_dlg.drawer_spinboxes.values()) == 150
        assert deduct_dlg.btn_submit.isEnabled() is True

        # Test direct drawer input syncs back to total_amount_spin
        deduct_dlg.drawer_spinboxes[5].setValue(0)
        deduct_dlg.drawer_spinboxes[1].setValue(50)
        deduct_dlg.drawer_spinboxes[2].setValue(50)
        assert deduct_dlg.total_amount_spin.value() == 120 # 50+50+0+20+0
        assert deduct_dlg.btn_submit.isEnabled() is True
        
        # Test smart balancing add mode on 5-drawer component
        add_dlg = BulkStockDialog(component=five_drawer_comp)
        add_dlg.radio_add.setChecked(True)
        add_dlg.total_amount_spin.setValue(100)
        # Verify water-filling allocation prioritizes drawer 11 (0 qty) and drawer 8 (20 qty)
        assert add_dlg.drawer_spinboxes[11].value() > add_dlg.drawer_spinboxes[5].value()
        assert add_dlg.drawer_spinboxes[8].value() > add_dlg.drawer_spinboxes[2].value()
        assert sum(s.value() for s in add_dlg.drawer_spinboxes.values()) == 100
        assert add_dlg.btn_submit.isEnabled() is True
        
        # Test equal distribute button
        add_dlg.btn_equal_distribute.click()
        assert add_dlg.drawer_spinboxes[1].value() == 20
        assert add_dlg.drawer_spinboxes[11].value() == 20
        assert sum(s.value() for s in add_dlg.drawer_spinboxes.values()) == 100

        add_dlg.close()
        deduct_dlg.close()
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

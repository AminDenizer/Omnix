from PyQt6.QtWidgets import QMessageBox, QWidget


def ask_persian_confirmation(parent: QWidget, title: str, message: str) -> bool:
    """Display a confirmation question modal dialog with Persian Yes/No buttons."""
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setIcon(QMessageBox.Icon.Question)
    
    btn_yes = msg_box.addButton("بله", QMessageBox.ButtonRole.YesRole)
    btn_no = msg_box.addButton("خیر", QMessageBox.ButtonRole.NoRole)
    
    btn_yes.setObjectName("successBtn")
    btn_no.setObjectName("secondaryBtn")
    
    msg_box.setDefaultButton(btn_no)
    msg_box.exec()
    
    return msg_box.clickedButton() == btn_yes

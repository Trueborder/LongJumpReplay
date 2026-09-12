import tkinter as tk

from src.theme import configure_popup


def test_configure_popup_centers_final_geometry_on_screen() -> None:
    root = tk.Tk()
    root.withdraw()
    popup = tk.Toplevel(root)
    try:
        configure_popup(popup, root)
        popup.geometry("320x180")
        root.update_idletasks()
        root.update()

        expected_x = max(0, (popup.winfo_screenwidth() - popup.winfo_width()) // 2)
        expected_y = max(0, (popup.winfo_screenheight() - popup.winfo_height()) // 2)
        assert abs(popup.winfo_x() - expected_x) <= 2
        assert abs(popup.winfo_y() - expected_y) <= 2
    finally:
        popup.destroy()
        root.destroy()

from PyQt6.QtGui import QColor

class ThemeEngine:
    """
    Dynamic QSS Stylesheet and Palette Generator supporting custom Accent Colors,
    frameless window borders, glassmorphism highlights, and polished DJ Crate styling.
    """

    @staticmethod
    def hex_to_rgb(hex_color: str) -> tuple:
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 6:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (196, 125, 99)

    @staticmethod
    def adjust_brightness(hex_color: str, factor: float) -> str:
        r, g, b = ThemeEngine.hex_to_rgb(hex_color)
        r = min(255, max(0, int(r * factor)))
        g = min(255, max(0, int(g * factor)))
        b = min(255, max(0, int(b * factor)))
        return f"#{r:02x}{g:02x}{b:02x}"

    @classmethod
    def generate_qss(cls, accent_hex: str = "#C47D63", theme: str = "Dark") -> str:
        r, g, b = cls.hex_to_rgb(accent_hex)
        accent_hover = cls.adjust_brightness(accent_hex, 1.15)
        accent_pressed = cls.adjust_brightness(accent_hex, 0.85)

        bg_main = "#121212"
        bg_card = "#1E1E1E"
        bg_sidebar = "#161616"
        bg_player = "#181716"
        text_primary = "#FFFFFF"
        text_secondary = "#A0A0A0"
        border_color = "#2A2A2A"

        if theme == "OLED Black":
            bg_main = "#000000"
            bg_card = "#0D0D0D"
            bg_sidebar = "#080808"
            bg_player = "#0A0A0A"
            border_color = "#1F1F1F"
        elif theme == "Soft Slate":
            bg_main = "#1E222A"
            bg_card = "#252B37"
            bg_sidebar = "#181C24"
            bg_player = "#1C2029"
            border_color = "#323A4B"

        qss = f"""
        /* Outer Frameless Central Widget */
        QWidget#centralWidget {{
            background-color: {bg_main};
            color: {text_primary};
            border: 1px solid {border_color};
            border-radius: 10px;
        }}

        QWidget {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            color: {text_primary};
        }}

        /* TitleBar */
        QWidget#titlebar {{
            background-color: {bg_sidebar};
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            border-bottom: 1px solid {border_color};
        }}
        QPushButton#win-btn {{
            background: transparent;
            border: none;
            border-radius: 4px;
        }}
        QPushButton#win-btn:hover {{
            background-color: rgba(255, 255, 255, 0.1);
        }}
        QPushButton#win-btn-close {{
            background: transparent;
            border: none;
            border-radius: 4px;
        }}
        QPushButton#win-btn-close:hover {{
            background-color: #B35959;
        }}

        /* Sidebar Navigation */
        QWidget#sidebar {{
            background-color: {bg_sidebar};
            border-right: 1px solid {border_color};
            border-bottom-left-radius: 10px;
        }}

        QPushButton[nav="true"] {{
            background-color: transparent;
            color: {text_secondary};
            border: none;
            border-left: 3px solid transparent;
            border-radius: 6px;
            padding: 10px 14px;
            text-align: left;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton[nav="true"]:hover {{
            background-color: rgba(255, 255, 255, 0.05);
            color: {text_primary};
        }}
        QPushButton[nav="true"]:checked {{
            background-color: rgba({r}, {g}, {b}, 0.16);
            color: {text_primary};
            border-left: 3px solid {accent_hex};
            font-weight: 700;
        }}

        /* Buttons */
        QPushButton {{
            background-color: {bg_card};
            color: {text_primary};
            border: 1px solid {border_color};
            border-radius: 6px;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: rgba(255, 255, 255, 0.08);
            border-color: {accent_hex};
        }}
        QPushButton:pressed {{
            background-color: rgba({r}, {g}, {b}, 0.3);
        }}

        QPushButton#download-btn {{
            background-color: {accent_hex};
            color: #FFFFFF;
            border: none;
            border-radius: 4px;
            font-weight: 700;
        }}
        QPushButton#download-btn:hover {{
            background-color: {accent_hover};
        }}

        /* Inputs */
        QLineEdit {{
            background-color: {bg_sidebar};
            color: {text_primary};
            border: 1px solid {border_color};
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 13px;
        }}
        QLineEdit:focus {{
            border-color: {accent_hex};
        }}

        /* Combo Boxes */
        QComboBox {{
            background-color: {bg_card};
            color: {text_primary};
            border: 1px solid {border_color};
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 12px;
        }}
        QComboBox:hover {{
            border-color: {accent_hex};
        }}
        QComboBox::drop-down {{
            border: none;
        }}
        QComboBox QAbstractItemView {{
            background-color: {bg_card};
            color: {text_primary};
            selection-background-color: {accent_hex};
            selection-color: #FFFFFF;
            border: 1px solid {border_color};
        }}

        /* List Widgets */
        QListWidget {{
            background-color: {bg_card};
            border: 1px solid {border_color};
            border-radius: 8px;
            outline: none;
            padding: 4px;
        }}
        QListWidget::item {{
            border-radius: 6px;
            margin-bottom: 2px;
            padding: 2px;
        }}
        QListWidget::item:hover {{
            background-color: rgba(255, 255, 255, 0.04);
        }}
        QListWidget::item:selected {{
            background-color: rgba({r}, {g}, {b}, 0.18);
            border: 1px solid {accent_hex};
        }}

        /* Search Cards & Item Rows */
        QLabel#result-title {{
            font-size: 13px;
            font-weight: 700;
            color: #FFFFFF;
        }}
        QLabel#result-meta {{
            font-size: 11px;
            color: {text_secondary};
        }}
        QLabel#track-row-title {{
            font-size: 13px;
            font-weight: 600;
            color: #FFFFFF;
        }}
        QLabel#track-row-title-playing {{
            font-size: 13px;
            font-weight: 700;
            color: {accent_hex};
        }}
        QLabel#track-row-title-missing {{
            font-size: 13px;
            font-weight: 600;
            color: #B35959;
            text-decoration: line-through;
        }}

        /* Player Bar */
        QWidget#playerBar {{
            background-color: {bg_player};
            border-top: 1px solid {border_color};
            border-bottom-left-radius: 10px;
            border-bottom-right-radius: 10px;
        }}
        QLabel#player-title {{
            font-size: 13px;
            font-weight: 700;
            color: #FFFFFF;
        }}
        QLabel#player-artist {{
            font-size: 11px;
            color: {text_secondary};
        }}
        QPushButton#play-btn {{
            background-color: {accent_hex};
            border: none;
            border-radius: 20px;
        }}
        QPushButton#play-btn:hover {{
            background-color: {accent_hover};
        }}
        QPushButton#control-btn {{
            background-color: transparent;
            border: 1px solid {border_color};
            border-radius: 16px;
        }}
        QPushButton#control-btn:hover {{
            background-color: rgba(255, 255, 255, 0.1);
        }}

        /* SoundCloud Waveform Player Slider */
        QSlider#playerSlider {{
            height: 38px;
            background: transparent;
            border: none;
        }}
        QSlider#playerSlider::groove:horizontal {{
            height: 38px;
            background: transparent;
            border: none;
        }}
        QSlider#playerSlider::handle:horizontal {{
            width: 0px;
            height: 38px;
            background: transparent;
            border: none;
        }}
        QSlider#playerSlider::sub-page:horizontal {{ background: transparent; }}
        QSlider#playerSlider::add-page:horizontal {{ background: transparent; }}

        /* Volume Slider */
        QSlider::groove:horizontal {{
            height: 4px;
            background: #282423;
            border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{
            background: {accent_hex};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            width: 12px;
            height: 12px;
            margin-top: -4px;
            margin-bottom: -4px;
            border-radius: 6px;
            background: #FFFFFF;
        }}

        /* Progress Bars */
        QProgressBar {{
            background-color: #222222;
            border: none;
            border-radius: 4px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {accent_hex};
            border-radius: 4px;
        }}
        """
        return qss

from PyQt6.QtGui import QColor

class ThemeEngine:
    """
    Tactile Pro-Audio QSS Stylesheet and Palette Generator.
    Supports customizable Accent Colors (Pioneer Cyan, Technics Amber, Serato Red, Xone Slate, Custom Hex),
    custom row density (Compact, Standard, Comfortable), and authentic studio console design.
    """

    ACCENT_PRESETS = [
        ("#C47D63", "Rust Amber"),
        ("#007AFF", "Pioneer Blue"),
        ("#FF9500", "Technics Amber"),
        ("#FF3B30", "Serato Red"),
        ("#30D158", "Emerald Green"),
        ("#8E8E93", "Xone Slate"),
        ("#00E5FF", "Cyber Cyan"),
        ("#D500F9", "Neon Violet"),
    ]

    @staticmethod
    def hex_to_rgb(hex_color: str) -> tuple:
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 6:
            try:
                return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            except ValueError:
                pass
        return (196, 125, 99)

    @staticmethod
    def adjust_brightness(hex_color: str, factor: float) -> str:
        r, g, b = ThemeEngine.hex_to_rgb(hex_color)
        r = min(255, max(0, int(r * factor)))
        g = min(255, max(0, int(g * factor)))
        b = min(255, max(0, int(b * factor)))
        return f"#{r:02x}{g:02x}{b:02x}"

    @classmethod
    def generate_qss(cls, accent_hex: str = "#C47D63", theme: str = "Dark", density: str = "standard") -> str:
        r, g, b = cls.hex_to_rgb(accent_hex)
        accent_hover = cls.adjust_brightness(accent_hex, 1.15)
        accent_pressed = cls.adjust_brightness(accent_hex, 0.85)

        # Authentic Studio Surface Tokens
        bg_main = "#0E0E10"
        bg_card = "#16161A"
        bg_sidebar = "#121215"
        bg_player = "#151518"
        bg_surface = "#1E1E24"
        text_primary = "#EDEDED"
        text_secondary = "#8E8E98"
        border_color = "#26262E"

        if theme == "OLED Black":
            bg_main = "#000000"
            bg_card = "#0A0A0D"
            bg_sidebar = "#050507"
            bg_player = "#08080A"
            bg_surface = "#121216"
            border_color = "#1A1A20"
        elif theme == "Soft Slate":
            bg_main = "#1A1D24"
            bg_card = "#222630"
            bg_sidebar = "#161920"
            bg_player = "#1E222A"
            bg_surface = "#2A303D"
            border_color = "#323846"

        # Row density metrics
        if density == "compact":
            row_pad_v = "2px"
            row_font_size = "11px"
        elif density == "comfortable":
            row_pad_v = "10px"
            row_font_size = "13px"
        else: # standard
            row_pad_v = "6px"
            row_font_size = "12px"

        qss = f"""
        /* Outer Frameless Central Container */
        QWidget#centralWidget {{
            background-color: {bg_main};
            color: {text_primary};
            border: 1px solid {border_color};
            border-radius: 8px;
        }}

        QWidget {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            color: {text_primary};
        }}

        /* TitleBar */
        QWidget#titlebar {{
            background-color: {bg_sidebar};
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            border-bottom: 1px solid {border_color};
        }}
        QPushButton#win-btn {{
            background: transparent;
            border: none;
            border-radius: 4px;
        }}
        QPushButton#win-btn:hover {{
            background-color: rgba(255, 255, 255, 0.08);
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
            border-bottom-left-radius: 8px;
        }}

        QPushButton[nav="true"] {{
            background-color: transparent;
            color: {text_secondary};
            border: none;
            border-left: 3px solid transparent;
            border-radius: 4px;
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
            background-color: {bg_surface};
            color: {text_primary};
            border: 1px solid {border_color};
            border-radius: 4px;
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

        /* Filter Chips */
        QPushButton[filter_chip="true"] {{
            background-color: {bg_surface};
            color: {text_secondary};
            border: 1px solid {border_color};
            border-radius: 12px;
            padding: 3px 10px;
            font-size: 11px;
            font-weight: 600;
        }}
        QPushButton[filter_chip="true"]:hover {{
            background-color: rgba(255, 255, 255, 0.08);
            color: {text_primary};
        }}
        QPushButton[filter_chip="true"]:checked {{
            background-color: rgba({r}, {g}, {b}, 0.20);
            color: #FFFFFF;
            border: 1px solid {accent_hex};
            font-weight: 700;
        }}

        /* Inputs */
        QLineEdit {{
            background-color: {bg_sidebar};
            color: {text_primary};
            border: 1px solid {border_color};
            border-radius: 4px;
            padding: 7px 12px;
            font-size: 13px;
        }}
        QLineEdit:focus {{
            border-color: {accent_hex};
        }}

        /* Combo Boxes */
        QComboBox {{
            background-color: {bg_surface};
            color: {text_primary};
            border: 1px solid {border_color};
            border-radius: 4px;
            padding: 5px 10px;
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

        /* Scroll Area & Scrollbars */
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background: {bg_sidebar};
            width: 8px;
            margin: 0;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: #2A2A34;
            min-height: 24px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #3E3E4C;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background: {bg_sidebar};
            height: 8px;
            margin: 0;
            border-radius: 4px;
        }}
        QScrollBar::handle:horizontal {{
            background: #2A2A34;
            min-width: 24px;
            border-radius: 4px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: #3E3E4C;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}

        /* List Widgets */
        QListWidget {{
            background-color: {bg_card};
            border: 1px solid {border_color};
            border-radius: 6px;
            outline: none;
            padding: 4px;
        }}
        QListWidget::item {{
            border-radius: 4px;
            margin-bottom: 2px;
            padding: {row_pad_v} 6px;
        }}
        QListWidget::item:hover {{
            background-color: rgba(255, 255, 255, 0.04);
        }}
        QListWidget::item:selected {{
            background-color: rgba({r}, {g}, {b}, 0.16);
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
            font-size: {row_font_size};
            font-weight: 600;
            color: #FFFFFF;
        }}
        QLabel#track-row-title-playing {{
            font-size: {row_font_size};
            font-weight: 700;
            color: {accent_hex};
        }}
        QLabel#track-row-title-missing {{
            font-size: {row_font_size};
            font-weight: 600;
            color: #B35959;
            text-decoration: line-through;
        }}

        /* Player Bar */
        QWidget#playerBar {{
            background-color: {bg_player};
            border-top: 1px solid {border_color};
            border-bottom-left-radius: 8px;
            border-bottom-right-radius: 8px;
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
            border-radius: 18px;
        }}
        QPushButton#play-btn:hover {{
            background-color: {accent_hover};
        }}
        QPushButton#control-btn {{
            background-color: transparent;
            border: 1px solid {border_color};
            border-radius: 14px;
        }}
        QPushButton#control-btn:hover {{
            background-color: rgba(255, 255, 255, 0.08);
        }}

        /* Tooltip */
        QToolTip {{
            background-color: #1A1A20;
            color: #EDEDED;
            border: 1px solid #333340;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
        }}

        /* SoundCloud Waveform Player Slider */
        QSlider#playerSlider {{
            height: 48px;
            background: transparent;
            border: none;
        }}
        QSlider#playerSlider::groove:horizontal {{
            height: 48px;
            background: transparent;
            border: none;
        }}
        QSlider#playerSlider::handle:horizontal {{
            width: 0px;
            height: 48px;
            background: transparent;
            border: none;
        }}
        QSlider#playerSlider::sub-page:horizontal {{ background: transparent; }}
        QSlider#playerSlider::add-page:horizontal {{ background: transparent; }}

        /* Volume Slider */
        QSlider::groove:horizontal {{
            height: 4px;
            background: #24242C;
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
            background-color: #1A1A20;
            border: none;
            border-radius: 3px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {accent_hex};
            border-radius: 3px;
        }}
        """
        return qss

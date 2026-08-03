"""术语表页：管理日译中专有名词对照。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class GlossaryPage(QWidget):
    """术语表页面。"""

    def __init__(self, config, glossary) -> None:
        super().__init__()
        self._config = config
        self._glossary = glossary
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        """构建界面。"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("术语表")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        self._enabled_check = QCheckBox("启用术语表（翻译前自动替换专有名词）")
        self._enabled_check.stateChanged.connect(self._toggle_enabled)
        layout.addWidget(self._enabled_check)

        hint = QLabel(
            "说明：勾选启用后，翻译前会自动将匹配的日文专名替换为中文，并作为参考发送给 DeepSeek。"
            "采用最长匹配，专名建议优先整理后一次性导入。"
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        add_row = QHBoxLayout()
        self._jp_edit = QLineEdit()
        self._jp_edit.setPlaceholderText("日文原名（如 リムル）")
        self._cn_edit = QLineEdit()
        self._cn_edit.setPlaceholderText("中文译名（如 利姆鲁）")
        self._add_btn = QPushButton("添加")
        self._add_btn.clicked.connect(self._add_pair)
        add_row.addWidget(self._jp_edit, 1)
        add_row.addWidget(self._cn_edit, 1)
        add_row.addWidget(self._add_btn)
        layout.addLayout(add_row)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["日文", "中文"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        self._delete_btn = QPushButton("删除选中")
        self._delete_btn.clicked.connect(self._delete_selected)
        self._clear_btn = QPushButton("清空")
        self._clear_btn.clicked.connect(self._clear_all)
        self._count_label = QLabel()
        self._count_label.setObjectName("subtitleLabel")
        self._import_btn = QPushButton("导入...")
        self._import_btn.clicked.connect(self._import_json)
        self._export_btn = QPushButton("导出...")
        self._export_btn.clicked.connect(self._export_json)
        btn_row.addWidget(self._delete_btn)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self._count_label)
        btn_row.addWidget(self._import_btn)
        btn_row.addWidget(self._export_btn)
        layout.addLayout(btn_row)

    # ---------- 操作 ----------

    def _toggle_enabled(self, state: int) -> None:
        """切换启用状态。"""
        self._glossary.enabled = state == Qt.Checked
        self._glossary.save()
        self._config.set("glossary", "enabled", self._glossary.enabled)

    def _add_pair(self) -> None:
        """添加词条。"""
        jp = self._jp_edit.text().strip()
        cn = self._cn_edit.text().strip()
        if not jp or not cn:
            QMessageBox.warning(self, "提示", "请输入完整的日文原名与中文译名。")
            return
        self._glossary.add(jp, cn)
        self._glossary.save()
        self._jp_edit.clear()
        self._cn_edit.clear()
        self._reload()

    def _delete_selected(self) -> None:
        """删除选中词条。"""
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        for row in rows:
            jp = self._table.item(row, 0).text()
            self._glossary.remove(jp)
        if rows:
            self._glossary.save()
            self._reload()

    def _clear_all(self) -> None:
        """清空全部词条。"""
        if not self._glossary.pairs():
            return
        ret = QMessageBox.question(
            self, "确认", "确定清空所有词条吗？", QMessageBox.Yes | QMessageBox.No
        )
        if ret == QMessageBox.Yes:
            self._glossary.clear()
            self._glossary.save()
            self._reload()

    def _import_json(self) -> None:
        """从 JSON 导入词条。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入术语表", "", "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        try:
            count = self._glossary.import_from(path)
            self._glossary.save()
            self._reload()
            QMessageBox.information(self, "导入完成", f"已导入 {count} 条词条。")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "导入失败", f"无法导入术语表：{exc}")

    def _export_json(self) -> None:
        """导出词条到 JSON。"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出术语表", "glossary.json", "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            self._glossary.export(path)
            QMessageBox.information(self, "导出完成", f"已导出到 {path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "导出失败", f"无法导出术语表：{exc}")

    def _reload(self) -> None:
        """刷新表格。"""
        self._enabled_check.setChecked(bool(self._glossary.enabled))
        pairs = self._glossary.pairs()
        self._table.setRowCount(len(pairs))
        for row, (jp, cn) in enumerate(pairs):
            self._table.setItem(row, 0, QTableWidgetItem(jp))
            self._table.setItem(row, 1, QTableWidgetItem(cn))
        self._count_label.setText(f"共 {len(pairs)} 条")

"""术语表页面

管理「日文 -> 中文」术语对照：
- 新增 / 删除 / 清空
- 导入导出（JSON）
- 启用开关（影响翻译时是否套用）
"""
from __future__ import annotations

from pathlib import Path

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
    """术语表页面"""

    def __init__(self, config, glossary) -> None:
        super().__init__()
        self._config = config
        self._glossary = glossary
        self._build_ui()
        self._reload()

    # ---------- 界面构建 ----------

    def _build_ui(self) -> None:
        """构建界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 顶部开关与操作
        top = QHBoxLayout()
        self._enabled_check = QCheckBox("启用术语表（翻译前自动替换专有名词）")
        self._enabled_check.stateChanged.connect(self._toggle_enabled)
        top.addWidget(self._enabled_check)
        top.addStretch(1)
        layout.addLayout(top)

        # 使用说明
        hint = QLabel(
            "说明：勾选启用后，翻译前会自动将匹配的日文专名替换为中文，"
            "并作为参考发送给 DeepSeek。采用最长匹配，专名建议优先整理后一次性导入。"
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 新增行
        add_row = QHBoxLayout()
        self._jp_edit = QLineEdit()
        self._jp_edit.setPlaceholderText("日文原名（如 リムル）")
        self._cn_edit = QLineEdit()
        self._cn_edit.setPlaceholderText("中文译名（如 利姆鲁）")
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._add_pair)
        add_row.addWidget(self._jp_edit, 1)
        add_row.addWidget(self._cn_edit, 1)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        # 表格
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["日文", "中文"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self._table, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        self._delete_btn = QPushButton("删除选中")
        self._delete_btn.clicked.connect(self._delete_selected)
        self._clear_btn = QPushButton("清空")
        self._clear_btn.clicked.connect(self._clear_all)
        self._import_btn = QPushButton("导入...")
        self._import_btn.clicked.connect(self._import_json)
        self._export_btn = QPushButton("导出...")
        self._export_btn.clicked.connect(self._export_json)
        self._count_label = QLabel()
        btn_row.addWidget(self._delete_btn)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self._count_label)
        btn_row.addWidget(self._import_btn)
        btn_row.addWidget(self._export_btn)
        layout.addLayout(btn_row)

    # ---------- 事件 ----------

    def _toggle_enabled(self) -> None:
        """切换启用状态"""
        self._glossary.enabled = self._enabled_check.isChecked()
        self._config.set("glossary", "enabled", self._enabled_check.isChecked())

    def _add_pair(self) -> None:
        """添加术语对"""
        jp = self._jp_edit.text().strip()
        cn = self._cn_edit.text().strip()
        if not jp or not cn:
            QMessageBox.warning(self, "输入不完整", "请填写日文与中文两项。")
            return
        self._glossary.add(jp, cn)
        self._jp_edit.clear()
        self._cn_edit.clear()
        self._reload()

    def _delete_selected(self) -> None:
        """删除选中行"""
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        for row in rows:
            item = self._table.item(row, 0)
            if item:
                self._glossary.remove(item.text())
        self._reload()

    def _clear_all(self) -> None:
        """清空术语表"""
        ret = QMessageBox.question(self, "清空", "确定清空全部术语？")
        if ret != QMessageBox.Yes:
            return
        self._glossary.clear()
        self._reload()

    def _import_json(self) -> None:
        """从 JSON 导入术语表"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入术语表", "", "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            count = self._glossary.import_from(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", f"无法读取文件：{exc}")
            return
        QMessageBox.information(self, "导入完成", f"已导入 {count} 条术语。")
        self._reload()

    def _export_json(self) -> None:
        """导出术语表为 JSON"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出术语表", "glossary.json", "JSON 文件 (*.json)"
        )
        if not path:
            return
        self._glossary.export(Path(path))
        QMessageBox.information(self, "导出完成", f"已导出到：{path}")

    # ---------- 刷新 ----------

    def _reload(self) -> None:
        """重新加载术语表到表格"""
        self._enabled_check.setChecked(bool(self._glossary.enabled))
        pairs = self._glossary.pairs()
        self._table.setRowCount(len(pairs))
        for row, (jp, cn) in enumerate(pairs):
            self._table.setItem(row, 0, QTableWidgetItem(jp))
            self._table.setItem(row, 1, QTableWidgetItem(cn))
        self._count_label.setText(f"共 {len(pairs)} 条")

"""课表导入页：选文件 / 粘文本 / 认截图 → 预览勾选 → 导出。

页面只依赖 :class:`~labkit.ui.kit.Kit` 与 :mod:`labkit.ttimport.api`，
既能在 lab 里独立跑，将来也能整体搬进主程序当作一个新页面。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHeaderView, QProgressBar, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..common import paths
from ..ttimport import api
from .kit import Kit

COLUMNS = ("", "课名", "星期", "节次", "周次", "教师", "地点", "提示")
EDITABLE = {1: "name", 4: "weeks", 5: "teacher", 6: "location"}
FILE_FILTER = (
    "课表文件 (*.pdf *.xlsx *.xlsm *.csv *.tsv *.txt *.png *.jpg *.jpeg *.bmp *.webp);;"
    "PDF (*.pdf);;"
    "表格 (*.xlsx *.xlsm *.csv *.tsv *.txt);;"
    "截图 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)"
)

#: OCR 引擎状态只探测一次（第一次探测要 1~3 秒）
_OCR_STATE: tuple[bool, str] | None = None


def ocr_state(refresh: bool = False) -> tuple[bool, str]:
    """截图识别可用性。

    主程序里走 :mod:`campus_planner.lab_ocr`（子进程 + ``lab/.venv``）；
    单独在 lab 里跑时退回落回 ``api.ocr_status()``。探测失败一律降级成
    ``(False, 说明)``，绝不让导入页因为 OCR 挂掉而开不起来。
    """
    global _OCR_STATE
    if _OCR_STATE is None or refresh:
        try:
            from campus_planner import lab_ocr

            _OCR_STATE = lab_ocr.status(refresh=refresh)
        except Exception as exc:  # noqa: BLE001 - 探测失败降级，不阻断页面
            _OCR_STATE = (False, f"OCR 引擎不可用：{type(exc).__name__}: {exc}")
    return _OCR_STATE


class _ImportWorker(QObject):
    """后台识别线程 —— 解决「识别时界面未响应」。

    OCR / PDF 解析要几十秒，之前直接在界面线程里同步调用，窗口会整窗冻结。
    这里把解析挪进 :class:`QThread`，进度通过 ``progress`` 信号回主线程刷新，
    结果 / 异常分别走 ``done`` / ``failed``。
    """

    progress = Signal(float, str, str)   # 百分比, 描述, 预计剩余
    done = Signal(object)                # ImportResult
    failed = Signal(str)
    finished = Signal()                  # run() 结束（供线程退出 / 释放 worker）

    def __init__(self, targets):
        super().__init__()
        self._targets = list(targets)

    def run(self) -> None:
        def on_progress(state) -> None:
            self.progress.emit(float(state.percent), str(state.text), str(state.eta_text))

        try:
            images = [Path(item) for item in self._targets
                      if Path(item).suffix.lower() in api.IMAGE_SUFFIXES]
            if images:
                # 截图走子进程 OCR（onnxruntime 只在 lab/.venv），与表格/PDF 混排时一起合并
                results = [self._recognize(image, on_progress) for image in images]
                rest = [item for item in self._targets if Path(item) not in images]
                if rest:
                    results.append(api.parse_many(rest, progress=on_progress))
                if len(results) == 1:
                    # 单来源：保留它自己的 source（ocr / excel / csv…）
                    result = results[0]
                else:
                    from ..ttimport.merge import merge_results  # noqa: PLC0415
                    result = merge_results(results, source="merged")
            elif len(self._targets) > 1:
                result = api.parse_many(self._targets, progress=on_progress)
            else:
                result = api.parse_file(self._targets[0], progress=on_progress)
        except Exception as exc:  # noqa: BLE001 - 失败也要回到主线程提示
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            self.finished.emit()
            return
        self.done.emit(result)
        self.finished.emit()

    @staticmethod
    def _recognize(image: Path, on_progress):
        """识别单张截图；进度量纲与 :func:`api.parse_file` 一致（0~1）。"""
        from campus_planner import lab_ocr

        class _State:
            __slots__ = ("percent", "text", "eta_text")

        def report(percent: float, text: str = "") -> None:
            state = _State()
            state.percent = max(0.0, min(1.0, float(percent)))
            state.text = text
            state.eta_text = ""
            on_progress(state)

        return lab_ocr.recognize(image, progress=report)


class ImportPage(QWidget):
    """一个完整的导入流程页。

    ``applied`` 在用户点「导入到课表」时发出，载荷是一份可直接落进主程序
    课表的数据（``courses`` / ``periods`` / ``total_weeks``），由宿主页面负责写库。
    """

    applied = Signal(object)

    def __init__(self, kit: Kit, toast=None, parent=None):
        super().__init__(parent)
        self.kit = kit
        self.toast = toast
        self.result = None
        self._loading = False
        self._busy_flag = False
        self._thread: QThread | None = None
        self.setAcceptDrops(True)
        self._build()

    # ------------------------------------------------------------------ 外观
    def _build(self) -> None:
        theme = self.kit.theme
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        bar = self.kit.card()
        bar_lay = self.kit.card_layout(bar, margins=(16, 12, 16, 12), spacing=10)
        bar_lay.addWidget(self.kit.row(
            self.kit.title("课表导入"),
            self.kit.chip("Excel / CSV", "green"),
            self.kit.chip("粘贴文本", "blue"),
            self.kit.chip("截图 OCR", "purple"),
        ))

        self.file_btn = self.kit.button("选择文件…", "upload", "primary")
        self.clip_btn = self.kit.button("粘贴文本", "doc")
        self.image_btn = self.kit.button("识别截图", "search")
        self.sample_btn = self.kit.button("载入样例", "list")
        self.clear_btn = self.kit.button("清空", "trash")
        self.file_btn.clicked.connect(self.pick_files)
        self.clip_btn.clicked.connect(self.load_clipboard)
        self.image_btn.clicked.connect(self.pick_image)
        self.sample_btn.clicked.connect(self.load_samples)
        self.clear_btn.clicked.connect(self.clear)
        bar_lay.addWidget(self.kit.row(
            self.file_btn, self.clip_btn, self.image_btn, self.sample_btn, self.clear_btn,
            None, self.kit.text("学期总周数", 11.5), self._make_spin(),
        ))
        self.status = self.kit.text("等待导入。可以拖文件进来，或点上面的按钮。", 11.5)
        bar_lay.addWidget(self.status)

        # 识别进度：进度条 + 百分比/剩余时间（识别是后台线程，这里只被动刷新）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar{background:rgba(255,255,255,170);border:none;border-radius:4px;}"
            f"QProgressBar::chunk{{background:{theme.C_BLUE};border-radius:4px;}}"
        )
        bar_lay.addWidget(self.progress_bar)
        self.progress_text = self.kit.text("", 11.5, theme.C_SUB)
        self.progress_text.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.progress_text.setVisible(False)
        bar_lay.addWidget(self.progress_text)

        outer.addWidget(bar)

        table_card = self.kit.card()
        table_lay = self.kit.card_layout(table_card, margins=(10, 8, 10, 10), spacing=8)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked
                                   | QTableWidget.EditTrigger.EditKeyPressed)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 34)
        self.table.setColumnWidth(7, 210)
        self.table.setStyleSheet(
            f"QTableWidget{{background:transparent;border:none;}}"
            f"QTableWidget::item{{padding:5px 6px;border-bottom:1px solid rgba(34,52,86,20);}}"
            f"QTableWidget::indicator{{width:15px;height:15px;}}"
            f"QTableWidget::indicator:unchecked{{border:1px solid rgba(34,52,86,90);"
            f"border-radius:4px;background:rgba(255,255,255,235);}}"
            f"QTableWidget::indicator:checked{{border:1px solid {theme.C_BLUE};"
            f"border-radius:4px;background:{theme.C_BLUE};}}"
            f"QHeaderView::section{{background:transparent;border:none;"
            f"border-bottom:1px solid rgba(34,52,86,36);color:{theme.C_SUB};padding:6px 6px;}}"
        )
        self.table.itemChanged.connect(self._on_item_changed)
        table_lay.addWidget(self.table, 1)

        self.hint = self.kit.text(
            "还没有课程。\n\n把 Excel / CSV / 截图 / 文本拖进窗口，或点上面的「载入样例」先看看效果。",
            11.5, theme.C_MUTED, wrap=True)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        table_lay.addWidget(self.hint, 1)

        self.issues = self.kit.text("", 11.5, theme.C_AMBER, wrap=True)
        table_lay.addWidget(self.issues)

        self.export_btn = self.kit.button("导出 JSON", "download", "soft")
        self.copy_btn = self.kit.button("复制预览", "copy")
        self.all_btn = self.kit.button("全选", "check")
        self.none_btn = self.kit.button("全不选", "close")
        self.apply_btn = self.kit.button("导入到课表", "check", "primary")
        self.count_label = self.kit.text("", 11.5)
        self.export_btn.clicked.connect(self.export)
        self.copy_btn.clicked.connect(self.copy_preview)
        self.all_btn.clicked.connect(lambda: self._set_all(True))
        self.none_btn.clicked.connect(lambda: self._set_all(False))
        self.apply_btn.clicked.connect(self.on_apply)
        table_lay.addWidget(self.kit.row(
            self.count_label, None, self.all_btn, self.none_btn, self.copy_btn, self.export_btn,
            self.apply_btn,
        ))
        outer.addWidget(table_card, 1)

        self._update_buttons()

    def _make_spin(self) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(1, 30)
        spin.setValue(16)
        spin.setFixedWidth(64)
        spin.setFixedHeight(30)
        spin.setFont(self.kit.theme.font(11.5))
        spin.setToolTip("整学期有多少周。它决定「1-16周」是全周还是只上前 16 周。")
        spin.setStyleSheet(
            "QSpinBox{background:rgba(255,255,255,220);border:1px solid rgba(34,52,86,40);"
            "border-radius:8px;padding:0 6px;}"
        )
        spin.valueChanged.connect(self._on_total_changed)
        self.total_spin = spin
        return spin

    # ------------------------------------------------------------------ 导入
    def pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择课表文件", str(paths.SAMPLE_DIR),
                                                FILE_FILTER)
        if files:
            self.load_paths(files)

    def pick_image(self) -> None:
        ready, reason = ocr_state()
        if not ready:
            self._warn("截图识别不可用", reason)
            return
        file, _ = QFileDialog.getOpenFileName(self, "选择课表截图", str(paths.SAMPLE_DIR),
                                              "截图 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if file:
            self.load_paths([file])

    def load_paths(self, files) -> None:
        """载入一个或多个文件。

        多个文件会走 :func:`api.parse_many`，**把 PDF / 多张照片 / 表格合并成同一张课表**
        （同天同节次同名去重、周次取并集、教师/地点互补）。
        """
        targets = [Path(item) for item in files]

        # 图片需要 OCR 引擎；PDF 只需要 pymupdf，两者可用性分开检查
        images = [p for p in targets if p.suffix.lower() in api.IMAGE_SUFFIXES]
        if images:
            ready, reason = ocr_state()
            if not ready:
                self._warn("跳过截图", f"{images[0].name}：{reason}")
                targets = [p for p in targets if p not in images]
        pdfs = [p for p in targets if p.suffix.lower() in api.PDF_SUFFIXES]
        if pdfs:
            pdf_ok, pdf_why = api.pdf_status()
            if not pdf_ok:
                self._warn("跳过 PDF", f"{pdfs[0].name}：{pdf_why}")
                targets = [p for p in targets if p not in pdfs]
        if not targets:
            return

        self._start_worker(targets)

    # ------------------------------------------------------------------ 后台识别
    def _start_worker(self, targets) -> None:
        """把识别放到后台线程，界面不再卡死；进度条实时显示百分比与剩余时间。"""
        self._busy(True, f"正在解析 {len(targets)} 个文件…")
        self._busy_flag = True
        self.progress_bar.setValue(0)
        self.progress_text.setText("准备中…")
        self.progress_bar.setVisible(True)
        self.progress_text.setVisible(True)
        self._update_buttons()

        thread = QThread(self)
        worker = _ImportWorker(targets)
        worker.moveToThread(thread)
        worker.progress.connect(self._on_progress)
        worker.done.connect(self._on_worker_done)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._clear_thread(thread))
        thread.started.connect(worker.run)
        self._thread, self._worker = thread, worker
        thread.start()

    def _on_progress(self, percent: float, text: str, eta: str) -> None:
        self.progress_bar.setValue(int(percent * 10))   # 0~1000
        self.progress_text.setText(f"{percent:5.1f}%　{text}　剩余 {eta}")

    def _on_worker_done(self, result) -> None:
        self._finish_busy()
        self._set_result(result)

    def _on_worker_failed(self, message: str) -> None:
        self._finish_busy()
        self._warn("导入失败", message)

    def _finish_busy(self) -> None:
        self.progress_bar.setVisible(False)
        self.progress_text.setVisible(False)
        self._busy_flag = False
        self._busy(False)
        self._update_buttons()

    def stop(self) -> None:
        """页面关闭 / 主题重建时停掉后台线程。

        否则 ``QThread`` 会在工作线程仍在解析时被销毁，Qt 会直接警告
        ``QThread: Destroyed while thread '' is still running`` 甚至崩溃。
        """
        thread = getattr(self, "_thread", None)
        if thread is not None and thread.isRunning():
            thread.quit()
            if not thread.wait(5000):
                thread.terminate()
                thread.wait(1000)
        self._thread = None

    def _clear_thread(self, thread) -> None:
        if self._thread is thread:
            self._thread = None

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self.stop()
        super().closeEvent(event)

    def load_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        if not text.strip():
            self._warn("剪贴板是空的", "先在教务系统里复制「全部课程清单」，再点这个按钮。")
            return
        self._set_result(api.parse_clipboard(text))

    def load_samples(self) -> None:
        folder = paths.SAMPLE_DIR
        if not folder.exists():
            self._warn("没有样例", "先跑 py -3 lab/tools/make_samples.py 生成样例文件。")
            return
        self.load_paths(sorted(p for p in folder.iterdir() if p.is_file()))

    def load_demo(self) -> None:
        """离屏自检用：只载入**不需要 OCR** 的样例（跳过截图）。

        ``load_samples`` 会把截图也一起拖进来，截图识别要加载 onnxruntime（首次 1~3 秒
        甚至更久），离屏自检不需要走这条路，否则整张自检图会等很久。
        """
        folder = paths.SAMPLE_DIR
        if not folder.exists():
            return
        files = sorted(
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() not in api.IMAGE_SUFFIXES
        )
        if files:
            self.load_paths(files)

    def clear(self) -> None:
        self.result = None
        self.table.setRowCount(0)
        self.status.setText("等待导入。可以拖文件进来，或点上面的按钮。")
        self.count_label.setText("")
        self.issues.setText("")
        self._update_buttons()

    def _set_result(self, result) -> None:
        self.result = result
        if result.total_weeks:
            self._loading = True
            self.total_spin.setValue(int(result.total_weeks))
            self._loading = False
        self.refresh()
        if self.toast is not None:
            self.toast.show_message(api.summarize(result), "ok" if result.courses else "warn")

    # ------------------------------------------------------------------ 刷新
    def refresh(self) -> None:
        result = self.result
        self._loading = True
        try:
            self.table.setRowCount(0)
            if result is None:
                return
            for row, course in enumerate(result.courses):
                self.table.insertRow(row)
                check = QTableWidgetItem("")
                check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                               | Qt.ItemFlag.ItemIsSelectable)
                check.setCheckState(Qt.CheckState.Checked if course.selected
                                    else Qt.CheckState.Unchecked)
                self.table.setItem(row, 0, check)
                values = (course.name, course.weekday_name, course.periods_label,
                          course.weeks_label(result.total_weeks), course.teacher, course.location)
                for offset, value in enumerate(values, start=1):
                    item = QTableWidgetItem(str(value))
                    if offset not in EDITABLE:
                        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    else:
                        item.setToolTip("双击可修改")
                    self.table.setItem(row, offset, item)
                hint = "；".join(course.issues)
                if hint:
                    text = hint if len(hint) <= 18 else hint[:18] + "…"
                    hint_item = QTableWidgetItem(text)
                    hint_item.setForeground(self.kit.theme.color(self.kit.theme.C_AMBER))
                else:
                    hint_item = QTableWidgetItem("正常")
                    hint_item.setForeground(self.kit.theme.color(self.kit.theme.C_MUTED))
                hint_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                hint_item.setToolTip(hint or "没问题")
                self.table.setItem(row, 7, hint_item)
        finally:
            self._loading = False

        if result is None:
            self.status.setText("等待导入。可以拖文件进来，或点上面的按钮。")
            self.issues.setText("")
            self.count_label.setText("")
            self._update_buttons()
            return

        origin = {"excel": "Excel", "csv": "CSV/文本", "paste": "粘贴文本", "ocr": "截图 OCR",
                  "multi": "多来源", "manual": "手工"}.get(result.source, result.source or "未知")
        issues = sum(len(c.issues) for c in result.courses)
        self.status.setText(
            f"{api.summarize(result)}　·　来源：{origin}　·　作息 {len(result.periods)} 条"
            f"　·　待确认 {issues} 处")
        self.issues.setText("提示：" + "；".join(result.warnings[:6]) if result.warnings else "")
        self.issues.setVisible(bool(result.warnings))
        self.count_label.setText(f"共 {len(result.courses)} 门，已勾选 {len(result.selected)} 门")
        self._update_buttons()

    def _update_buttons(self) -> None:
        has = bool(self.result and self.result.courses)
        busy = self._busy_flag
        for button in (self.export_btn, self.copy_btn, self.all_btn, self.none_btn, self.apply_btn):
            button.setEnabled(has and not busy)
        for button in (self.file_btn, self.clip_btn, self.image_btn,
                       self.sample_btn, self.clear_btn):
            button.setEnabled(not busy)
        ready, reason = ocr_state() if _OCR_STATE is not None else (True, "")
        self.image_btn.setToolTip(reason if _OCR_STATE is not None else "从课表截图中识别课程")
        self.table.setVisible(has)
        self.hint.setVisible(not has)

    # ------------------------------------------------------------------ 交互
    def _set_all(self, selected: bool) -> None:
        if self.result is None or self._busy_flag:
            return
        for course in self.result.courses:
            course.selected = selected
        self.refresh()

    def _on_total_changed(self, value: int) -> None:
        if self._loading or self._busy_flag or self.result is None:
            return
        self.result.total_weeks = int(value)
        self.result.finalize()
        self.refresh()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or self._busy_flag or self.result is None:
            return
        row, col = item.row(), item.column()
        if row >= len(self.result.courses):
            return
        course = self.result.courses[row]
        if col == 0:
            course.selected = item.checkState() == Qt.CheckState.Checked
            self._update_buttons()
            self.count_label.setText(
                f"共 {len(self.result.courses)} 门，已勾选 {len(self.result.selected)} 门")
            return
        field = EDITABLE.get(col)
        if field is None:
            return
        text = item.text().strip()
        if field == "weeks":
            course.mode = "custom" if text else "all"
            course.weeks_text = text
            course.parity = ""
            course.week_list = []
            course.issues = [i for i in course.issues if "周次" not in i]
        else:
            setattr(course, field, text)
        self.result.finalize()
        self.refresh()

    # ------------------------------------------------------------------ 导入到课表
    def on_apply(self) -> None:
        """把勾选的课程交给宿主（课表页面）写入主程序数据。

        载荷只带 ``core.Course`` / ``core.Period`` 需要的字段，宿主可以直接
        ``core.Course(**item)`` 重建对象，不需要再碰 :mod:`labkit`。
        """
        result = self.result
        if result is None or not result.courses:
            return
        selected = result.selected
        if not selected:
            self._warn("没有课程", "至少勾选一门课再导入。")
            return
        self.applied.emit({
            "courses": [course.to_core_kwargs() for course in selected],
            "periods": api.build_periods(result),
            "total_weeks": int(result.total_weeks or 0),
            "source": result.source,
        })
        if self.toast is not None:
            self.toast.show_message(f"已提交 {len(selected)} 门课，请在课表中确认", "ok")

    # ------------------------------------------------------------------ 导出
    def export(self) -> None:
        if self.result is None:
            return
        target = paths.data_file(f"import/课表导入-{_stamp()}.json")
        saved = api.save_payload(self.result, target)
        if self.toast is not None:
            self.toast.show_message(f"已保存 {saved.name}（{len(self.result.selected)} 门课）", "ok")
        self.status.setText(f"已导出：{saved}")

    def copy_preview(self) -> None:
        if self.result is None:
            return
        rows = ["\t".join(COLUMNS[1:])]
        for course in self.result.selected:
            rows.append("\t".join((
                course.name, course.weekday_name, course.periods_label,
                course.weeks_label(self.result.total_weeks), course.teacher, course.location,
                "；".join(course.issues),
            )))
        QApplication.clipboard().setText("\n".join(rows))
        if self.toast is not None:
            self.toast.show_message(f"已复制 {len(self.result.selected)} 门课到剪贴板", "ok")

    # ------------------------------------------------------------------ 拖放
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        files = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        files = [item for item in files if item]
        if files:
            self.load_paths(files)
            event.acceptProposedAction()

    # ------------------------------------------------------------------ 杂项
    def _busy(self, active: bool, text: str = "") -> None:
        self._busy_flag = active
        if text:
            self.status.setText(text)
        if active:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.status.repaint()
        else:
            QApplication.restoreOverrideCursor()

    def _warn(self, title: str, detail: str) -> None:
        self.status.setText(f"{title}：{detail}")
        if self.toast is not None:
            self.toast.show_message(f"{title}：{detail}", "error", timeout=4200)


def _stamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d-%H%M%S")

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

from app.services.import_service import ImportService


def test_csv_import_preview_parses_export_shape() -> None:
    content = (
        "Дата,Тип,Сумма,Категория,Описание,Источник\n"
        "2026-03-28,expense,350.00,Еда,Обед,text\n"
        "2026-03-27,income,5000.00,Зарплата,,webapp\n"
    ).encode("utf-8")

    preview = ImportService().build_preview(filename="finance_month.csv", content=content)

    assert preview.supported is True
    assert preview.ready_to_import is True
    assert preview.total_rows == 2
    assert len(preview.importable_rows) == 2
    assert preview.importable_rows[0].category == "food"
    assert preview.importable_rows[1].tx_type == "income"
    assert preview.importable_rows[1].source == "webapp"


def test_xlsx_import_preview_parses_export_shape() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Транзакции"
    ws.append(["Дата", "Тип", "Сумма", "Категория", "Описание", "Источник"])
    ws.append(["2026-03-28", "expense", "900.00", "Транспорт", "Такси", "text"])

    buf = BytesIO()
    wb.save(buf)

    preview = ImportService().build_preview(filename="finance.xlsx", content=buf.getvalue())

    assert preview.supported is True
    assert preview.ready_to_import is True
    assert len(preview.importable_rows) == 1
    assert preview.importable_rows[0].category == "transport"
    assert preview.importable_rows[0].description == "Такси"


def test_pdf_import_is_safe_preview_only() -> None:
    preview = ImportService().build_preview(filename="statement.pdf", content=b"%PDF-1.4 fake")

    assert preview.supported is False
    assert preview.ready_to_import is False
    assert any("PDF-импорт" in item for item in preview.warnings)


def test_render_preview_mentions_dry_run_and_counts() -> None:
    content = (
        "Дата,Тип,Сумма,Категория,Описание,Источник\n"
        "2026-03-28,expense,350.00,Еда,Обед,text\n"
    ).encode("utf-8")

    preview = ImportService().build_preview(filename="finance.csv", content=content)
    message = ImportService().render_preview_message(preview)

    assert "Dry-run импорт" in message
    assert "Будет импортировано: 1" in message
    assert "До этого в базу ничего не пишется" in message

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.db.session import SessionLocal
from app.telegram.keyboards import done_keyboard
from app.telegram.handlers.common import _ensure_user

logger = logging.getLogger("finance_bot.telegram")

_IMPORT_TEMPLATE_CSV = (
    "date,amount,description,type,category\n"
    "2024-01-15,1500,Продукты Перекрёсток,expense,food\n"
    "2024-01-16,50000,Зарплата,income,salary\n"
    "2024-01-17,450,Такси домой,expense,transport\n"
)


def _import_preview_keyboard(ready: bool):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    if ready:
        rows = [
            [InlineKeyboardButton("✅ Импортировать", callback_data="import:confirm")],
            [InlineKeyboardButton("✕ Отменить", callback_data="import:cancel")],
        ]
    else:
        rows = [[InlineKeyboardButton("✕ Закрыть", callback_data="import:cancel")]]
    return InlineKeyboardMarkup(rows)


async def import_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Пришли CSV или XLSX файлом, и я сначала покажу dry-run превью.\n"
        "Сохраняю только после отдельного подтверждения.\n\n"
        "PDF пока только распознаю как неподдерживаемый безопасный сценарий, без автоимпорта.",
        reply_markup=done_keyboard(),
    )


async def document_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.services.import_service import ImportService

    message = update.effective_message
    if message is None or message.document is None:
        return

    filename = message.document.file_name or "document"
    detected_format = ImportService.detect_format(filename)
    if detected_format not in ImportService.SUPPORTED_EXTENSIONS:
        return

    placeholder = await message.reply_text("📥 Смотрю файл…")
    telegram_file = await context.bot.get_file(message.document.file_id)
    content = bytes(await telegram_file.download_as_bytearray())

    svc = ImportService()
    preview = svc.build_preview(filename=filename, content=content)

    if preview.ready_to_import and update.effective_user is not None:
        from app.models.transaction import Transaction as TxModel
        from sqlalchemy import select as sa_select
        from datetime import datetime as dt_cls
        user_id = update.effective_user.id
        with SessionLocal() as db:
            dates = [row.created_at for row in preview.importable_rows]
            date_from = dt_cls.fromisoformat(min(dates))
            date_to = dt_cls.fromisoformat(max(dates))
            stmt = sa_select(TxModel).where(
                TxModel.telegram_user_id == user_id,
                TxModel.created_at >= date_from,
                TxModel.created_at <= date_to,
            )
            existing_txs = list(db.scalars(stmt).all())
            existing_keys = {
                ImportService._dedup_key(
                    t.created_at.date().isoformat(),
                    f"{t.amount:.2f}",
                    t.description,
                )
                for t in existing_txs
            }
        preview = svc.apply_dedup(preview, existing_keys)

    if context.user_data is not None:
        context.user_data.pop("pending_import_rows", None)
        context.user_data.pop("pending_import_filename", None)
        if preview.ready_to_import:
            context.user_data["pending_import_rows"] = preview.to_pending_payload()
            context.user_data["pending_import_filename"] = preview.filename

    try:
        await placeholder.edit_text(
            svc.render_preview_message(preview),
            reply_markup=_import_preview_keyboard(preview.ready_to_import),
        )
    except BadRequest:
        await message.reply_text(
            svc.render_preview_message(preview),
            reply_markup=_import_preview_keyboard(preview.ready_to_import),
        )


async def import_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    action = query.data.removeprefix("import:")
    if action == "cancel":
        if context.user_data is not None:
            context.user_data.pop("pending_import_rows", None)
            context.user_data.pop("pending_import_filename", None)
        await query.edit_message_text("Импорт отменён.", reply_markup=done_keyboard(back_target="nav:menu"))
        return

    pending_rows = (context.user_data or {}).get("pending_import_rows")
    filename = (context.user_data or {}).get("pending_import_filename", "файл")
    if action != "confirm" or not pending_rows:
        await query.edit_message_text(
            "❌ Превью устарело. Пришли файл заново.",
            reply_markup=done_keyboard(back_target="nav:menu"),
        )
        return

    from datetime import date as date_cls
    from app.services.transaction_service import TransactionService

    imported_count = 0
    with SessionLocal() as db:
        _ensure_user(db, update)
        svc = TransactionService(db)
        for row in pending_rows:
            try:
                svc.create_imported(
                    update.effective_user.id,
                    tx_type=str(row["tx_type"]),
                    amount=str(row["amount"]),
                    category=str(row["category"]),
                    description=(str(row["description"]) if row.get("description") else None),
                    source=str(row.get("source") or "text"),
                    raw_input=f"import:{filename}:row:{row['row_number']}",
                    override_date=date_cls.fromisoformat(str(row["created_at"])),
                )
                imported_count += 1
            except Exception as exc:
                db.rollback()
                await query.edit_message_text(
                    f"❌ Импорт остановлен на строке {row['row_number']}: {exc}",
                    reply_markup=done_keyboard(back_target="nav:menu"),
                )
                return

    if context.user_data is not None:
        context.user_data.pop("pending_import_rows", None)
        context.user_data.pop("pending_import_filename", None)

    await query.edit_message_text(
        f"✅ Импортировал {imported_count} записей из {filename}.",
        reply_markup=done_keyboard(back_target="nav:operations"),
    )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import io

    from app.services.export_service import ExportService
    from app.services.transaction_service import TransactionService

    export_service = ExportService()
    period = "month"
    export_format = "csv"

    for arg in context.args:
        normalized = arg.strip().lower()
        if normalized in {"today", "week", "month", "all"}:
            period = export_service.normalize_period(normalized)
        elif normalized in {"csv", "xlsx", "excel"}:
            export_format = export_service.normalize_format(normalized)

    with SessionLocal() as db:
        _ensure_user(db, update)
        svc = TransactionService(db)
        items = svc.list_transactions(update.effective_user.id, limit=1000, offset=0, period=period)

    if not items:
        period_label = {"today": "сегодня", "week": "за неделю", "month": "за месяц", "all": "за всё время"}.get(period, period)
        await update.effective_message.reply_text(f"Записей {period_label} нет.", reply_markup=done_keyboard())
        return

    artifact = export_service.build(items, period=period, export_format=export_format)

    from telegram import InputFile, InlineKeyboardButton, InlineKeyboardMarkup

    template_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Шаблон для импорта", callback_data="export:template")
    ]])

    await update.effective_message.reply_document(
        document=InputFile(io.BytesIO(artifact.content), filename=artifact.filename),
        caption=artifact.caption,
        reply_markup=template_keyboard,
    )


async def export_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import io
    from telegram import InputFile

    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        if query.data == "export:template" and query.message:
            await query.message.reply_document(
                document=InputFile(io.BytesIO(_IMPORT_TEMPLATE_CSV.encode("utf-8")), filename="import_template.csv"),
                caption="📋 Шаблон для импорта\n\nЗаполни файл и используй /import для загрузки.",
            )
    except Exception:
        logger.exception("export_callback_handler error: data=%s", query.data)
    finally:
        try:
            await query.answer()
        except Exception:
            pass

"""Import and export adapters for the reviewed word bank."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from typing import Any


class WordBankIO:
    """Translate external word-bank formats into service save calls."""

    def __init__(self, save_word: Callable[..., dict[str, Any]], list_words: Callable[[], list[dict[str, Any]]]):
        self._save_word = save_word
        self._list_words = list_words

    def import_payload(self, payload: Any, filename: str | None = None) -> dict[str, Any]:
        if isinstance(payload, (list, tuple)):
            rows: list[Any] = list(payload)
        elif isinstance(payload, dict):
            rows = [payload]
        else:
            content = self._decode(payload)
            if (filename or "").lower().endswith(".json"):
                decoded = json.loads(content)
                rows = decoded if isinstance(decoded, list) else [decoded]
            elif (filename or "").lower().endswith(".csv") or self._looks_like_csv(content):
                rows = list(csv.DictReader(io.StringIO(content)))
            else:
                rows = [line.strip() for line in content.splitlines() if line.strip()]

        saved = []
        for row in rows:
            if isinstance(row, dict):
                word = row.get("word") or row.get("term") or row.get("normalized_word") or row.get("value")
                if not word:
                    continue
                syllables = row.get("syllables")
                if isinstance(syllables, str):
                    syllables = [item for item in syllables.split("-") if item]
                saved.append(self._save_word(
                    str(word),
                    syllables=syllables if isinstance(syllables, list) else None,
                    decoding=row.get("decoding") or row.get("formatted"),
                    pos=row.get("pos"),
                    family=row.get("family"),
                    notes=row.get("notes"),
                    source="import",
                ))
            elif row is not None and str(row).strip():
                saved.append(self._save_word(str(row).strip(), source="import"))
        return {"count": len(saved), "results": saved}

    def export(self, format_name: str = "csv") -> dict[str, Any]:
        format_key = (format_name or "csv").lower()
        rows = self._list_words()
        headers = [
            "word", "normalized_word", "decoding", "formatted", "syllables",
            "stressed_syllable_index", "cefr", "pos", "family", "source", "is_academic",
        ]
        values = [
            [
                row["word"], row["normalized_word"], row["decoding"], row["formatted"],
                "-".join(row["syllables"]), row["stressed_syllable_index"], row["cefr"],
                row.get("pos") or "", row.get("family") or "", row.get("source") or "word-bank",
                int(bool(row.get("is_academic", False))),
            ]
            for row in rows
        ]
        if format_key == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(values)
            return self._result(output.getvalue().encode("utf-8"), "text/csv; charset=utf-8", "word-bank.csv")
        if format_key == "xlsx":
            return self._export_xlsx(headers, values)
        if format_key == "ods":
            return self._export_ods(headers, values)
        raise ValueError("Unsupported export format. Use csv, xlsx, or ods.")

    @staticmethod
    def _decode(payload: Any) -> str:
        if isinstance(payload, (bytes, bytearray)):
            return payload.decode("utf-8-sig")
        if isinstance(payload, str):
            return payload
        return json.dumps(payload)

    @staticmethod
    def _looks_like_csv(content: str) -> bool:
        first_line = content.splitlines()[0] if content.splitlines() else ""
        return "," in first_line and "word" in first_line.lower()

    @staticmethod
    def _result(content: bytes, content_type: str, filename: str) -> dict[str, Any]:
        return {"content": content, "content_type": content_type, "filename": filename}

    @classmethod
    def _export_xlsx(cls, headers: list[str], values: list[list[Any]]) -> dict[str, Any]:
        try:
            from openpyxl import Workbook
        except ImportError as exc:
            raise RuntimeError("XLSX export requires openpyxl to be installed.") from exc
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "word_bank"
        sheet.append(headers)
        for value in values:
            sheet.append(value)
        buffer = io.BytesIO()
        workbook.save(buffer)
        return cls._result(
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "word-bank.xlsx",
        )

    @classmethod
    def _export_ods(cls, headers: list[str], values: list[list[Any]]) -> dict[str, Any]:
        try:
            from odf import opendocument, table, text
        except ImportError as exc:
            raise RuntimeError("ODS export requires odfpy to be installed.") from exc
        document = opendocument.OpenDocumentSpreadsheet()
        table_body = table.Table(name="word_bank")
        for row_values in [headers, *values]:
            row = table.TableRow()
            for value in row_values:
                cell = table.TableCell(valuetype="string")
                cell.addElement(text.P(text=str(value)))
                row.addElement(cell)
            table_body.addElement(row)
        document.spreadsheet.addElement(table_body)
        buffer = io.BytesIO()
        document.save(buffer)
        return cls._result(
            buffer.getvalue(),
            "application/vnd.oasis.opendocument.spreadsheet",
            "word-bank.ods",
        )


__all__ = ["WordBankIO"]

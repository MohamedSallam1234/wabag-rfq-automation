"""XLSX spreadsheet parsing helpers using openpyxl.

Opening the workbook also serves as the integrity check for ``.xlsx`` files and
distinguishes a real spreadsheet from a ``.docx`` or plain ZIP that merely shares
the OOXML magic bytes: those fail to load and become ``failed`` documents.
Legacy ``.xls`` is not parsed here (openpyxl cannot read it; no ``xlrd``).
"""

from openpyxl import load_workbook


def extract_xlsx_sheet_names(path: str) -> list[str]:
    """Return the sheet names of an ``.xlsx`` workbook.

    Args:
        path: Filesystem path to the workbook.

    Returns:
        The list of sheet names.

    Raises:
        Exception: If the file is not a readable ``.xlsx`` workbook.
    """
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()

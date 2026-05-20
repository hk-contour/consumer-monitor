"""Append flagged changes to the Signal Feedback Log tab in the master xlsx.

Columns: Date | Ticker | Company | Source URL | Summary of Change / Update |
         Signal or Noise? | Fundamental Theme | Notes / Action

We fill Date, Ticker, Company, Source URL, Summary. Analyst fills the rest.
"""

from __future__ import annotations

import time
from pathlib import Path

import openpyxl

from digest import Change

XLSX_PATH = Path(__file__).resolve().parent / "config" / "company_urls_jc.xlsx"


def append_changes(changes: list[Change], xlsx_path: Path = XLSX_PATH) -> None:
    if not changes:
        return
    wb = openpyxl.load_workbook(xlsx_path)
    if "Signal Feedback Log" not in wb.sheetnames:
        raise ValueError("Signal Feedback Log tab missing from xlsx")
    ws = wb["Signal Feedback Log"]
    today = time.strftime("%Y-%m-%d")
    for c in changes:
        ws.append([today, c.ticker, c.company, c.url, c.summary, "", "", ""])
    wb.save(xlsx_path)

import logging
import math
import re
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

BASE_URL = (
    "https://raw.githubusercontent.com/"
    "Shubhamnpk/yonepse/main/data/company"
)

FINANCIALS_URL = f"{BASE_URL}/financials.json"
METADATA_URL = f"{BASE_URL}/metadata.json"
RUN_METADATA_URL = f"{BASE_URL}/run_metadata.json"

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")
CACHE_SECONDS = 3600
MAX_DATA_AGE = timedelta(days=7)

DOCUMENT_BASE_URL = (
    "https://www.nepalstock.com.np/api/nots/security/"
    "fetchFiles?fileLocation="
)

REPORT_TYPES = {
    "Annual Report",
    "Quarterly Report",
}

QUARTERS = {
    "First Quarter",
    "Second Quarter",
    "Third Quarter",
    "Fourth Quarter",
}

FINANCIAL_FIELDS = (
    "pe",
    "eps",
    "paid_up_capital",
    "profit",
    "net_worth_per_share",
)

_cache = None
_cache_expires_at = 0


class FundamentalDataError(Exception):
    """Raised when financial data cannot be safely retrieved."""


def _validate_number(name, value):
    if value is None:
        return None

    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise FundamentalDataError(
            f"Invalid financial value: {name}"
        )

    return float(value)


def _parse_checked_timestamp(value):
    try:
        timestamp = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise FundamentalDataError(
            "Invalid financial-data check timestamp"
        ) from exc

    if timestamp.tzinfo is None:
        raise FundamentalDataError(
            "Financial-data timestamp has no timezone"
        )

    timestamp = timestamp.astimezone(NEPAL_TZ)

    if timestamp > datetime.now(NEPAL_TZ) + timedelta(minutes=5):
        raise FundamentalDataError(
            "Financial-data timestamp is in the future"
        )

    return timestamp


def _normalize_document(document):
    if not isinstance(document, dict):
        raise FundamentalDataError("Invalid financial document")

    submitted_date = document.get("submitted_date")
    path = document.get("path")

    if not isinstance(submitted_date, str) or not submitted_date:
        raise FundamentalDataError("Missing document submission date")

    if not isinstance(path, str) or not path.strip():
        raise FundamentalDataError("Missing financial document path")

    path = path.strip()

    if (
        path.startswith("/")
        or "\\" in path
        or ".." in path.split("/")
        or "?" in path
        or "#" in path
    ):
        raise FundamentalDataError("Unsafe financial document path")

    return {
        "submitted_date": submitted_date,
        "path": path,
        "url": DOCUMENT_BASE_URL + quote(path, safe="/"),
    }


def _normalize_report(report):
    if not isinstance(report, dict):
        raise FundamentalDataError("Invalid financial report")

    report_type = report.get("type")
    fiscal_year = report.get("fy")
    quarter = report.get("quarter")

    if report_type not in REPORT_TYPES:
        raise FundamentalDataError("Unknown financial report type")

    if not isinstance(fiscal_year, str) or not fiscal_year.strip():
        raise FundamentalDataError("Missing financial year")

    if report_type == "Annual Report" and quarter is not None:
        logger.warning(
            "Annual report has an unexpected quarter value: %s",
            quarter,
        )

    if report_type == "Quarterly Report" and quarter not in QUARTERS:
        raise FundamentalDataError("Invalid quarterly report period")

    normalized = {
        "type": report_type,
        "quarter": quarter,
        "fy": fiscal_year.strip(),
        "fy_nepali": report.get("fy_nepali"),
    }

    for field in FINANCIAL_FIELDS:
        normalized[field] = _validate_number(
            field,
            report.get(field),
        )

    documents = report.get("documents", [])

    if not isinstance(documents, list):
        raise FundamentalDataError("Invalid financial documents list")

    normalized["documents"] = [
        _normalize_document(document)
        for document in documents
    ]

    return normalized


def _period_key(report):
    return (
        report["type"],
        report["fy"],
        report["quarter"],
    )


def _financial_signature(report):
    return tuple(
        report[field]
        for field in FINANCIAL_FIELDS
    )


def _deduplicate_reports(reports):
    groups = {}

    for report in reports:
        groups.setdefault(_period_key(report), []).append(report)

    result = []

    for period_reports in groups.values():
        signatures = {
            _financial_signature(report)
            for report in period_reports
        }

        if len(signatures) == 1:
            merged = dict(period_reports[0])
            documents = {}

            for report in period_reports:
                for document in report["documents"]:
                    documents[document["path"]] = document

            merged["documents"] = list(documents.values())
            merged["status"] = "verified"
            result.append(merged)

        else:
            for report in period_reports:
                ambiguous = dict(report)
                ambiguous["status"] = "ambiguous"
                result.append(ambiguous)

    return sorted(
        result,
        key=lambda report: (
            report["fy"],
            report["quarter"] or "",
            report["type"],
        ),
        reverse=True,
    )


def _normalize_company(company):
    if not isinstance(company, dict):
        raise FundamentalDataError("Invalid company record")

    company_id = company.get("id")
    symbol = company.get("symbol")
    reports = company.get("reports")

    if (
        not isinstance(company_id, int)
        or isinstance(company_id, bool)
        or company_id <= 0
    ):
        raise FundamentalDataError("Invalid company ID")

    if (
        not isinstance(symbol, str)
        or not re.fullmatch(r"[A-Z0-9/]+", symbol.strip().upper())
    ):
        raise FundamentalDataError("Invalid company symbol")

    if not isinstance(reports, list):
        raise FundamentalDataError("Invalid company reports list")

    normalized_reports = [
        _normalize_report(report)
        for report in reports
    ]

    return {
        "id": company_id,
        "symbol": symbol.strip().upper(),
        "reports": _deduplicate_reports(normalized_reports),
    }


def _validate_dataset(payload, metadata, run_metadata):
    if not isinstance(payload, list):
        raise FundamentalDataError("Invalid financial dataset format")

    if not isinstance(metadata, dict):
        raise FundamentalDataError("Invalid financial metadata")

    if not isinstance(run_metadata, dict):
        raise FundamentalDataError("Invalid financial run metadata")

    expected_count = metadata.get("count")

    if (
        not isinstance(expected_count, int)
        or isinstance(expected_count, bool)
        or expected_count <= 0
        or expected_count != len(payload)
    ):
        raise FundamentalDataError(
            "Financial company count does not match metadata"
        )

    last_checked = _parse_checked_timestamp(
        run_metadata.get("financials_last_checked_at")
    )

    age = datetime.now(NEPAL_TZ) - last_checked

    if age > MAX_DATA_AGE:
        raise FundamentalDataError(
            "Financial dataset is older than seven days"
        )

    metadata_updated = metadata.get("last_updated")

    if not isinstance(metadata_updated, str) or not metadata_updated:
        raise FundamentalDataError(
            "Missing financial metadata update timestamp"
        )

    try:
        datetime.fromisoformat(metadata_updated)
    except ValueError as exc:
        raise FundamentalDataError(
            "Invalid financial metadata update timestamp"
        ) from exc

    companies = {}
    company_ids = set()

    for record in payload:
        company = _normalize_company(record)
        symbol = company["symbol"]

        if symbol in companies:
            raise FundamentalDataError(
                f"Duplicate company symbol: {symbol}"
            )

        if company["id"] in company_ids:
            raise FundamentalDataError(
                "Duplicate company ID"
            )

        companies[symbol] = company
        company_ids.add(company["id"])

    if not companies:
        raise FundamentalDataError(
            "Financial dataset contains no companies"
        )

    return {
        "companies": companies,
        "company_count": len(companies),
        "report_count": sum(
            len(company["reports"])
            for company in companies.values()
        ),
        "last_updated": metadata_updated,
        "last_checked_at": last_checked.isoformat(),
        "source": "YONEPSE financial reports",
    }


async def fetch_fundamental_data(force_refresh=False):
    global _cache, _cache_expires_at

    import time

    if (
        not force_refresh
        and _cache is not None
        and time.monotonic() < _cache_expires_at
    ):
        return _cache

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            responses = await __import__("asyncio").gather(
                client.get(FINANCIALS_URL),
                client.get(METADATA_URL),
                client.get(RUN_METADATA_URL),
            )

            for response in responses:
                response.raise_for_status()

            payload, metadata, run_metadata = (
                response.json() for response in responses
            )

    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Unable to retrieve financial dataset")
        raise FundamentalDataError(
            "Unable to retrieve NEPSE financial data"
        ) from exc

    try:
        result = _validate_dataset(
            payload,
            metadata,
            run_metadata,
        )
    except FundamentalDataError:
        logger.exception("Financial dataset validation failed")
        raise

    _cache = result
    _cache_expires_at = time.monotonic() + CACHE_SECONDS

    logger.info(
        "Financial dataset loaded: companies=%d reports=%d",
        result["company_count"],
        result["report_count"],
    )

    return result


async def get_company_financials(symbol, force_refresh=False):
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Please provide a company symbol")

    normalized_symbol = symbol.strip().upper()

    dataset = await fetch_fundamental_data(
        force_refresh=force_refresh
    )

    return dataset["companies"].get(normalized_symbol)


def clear_fundamental_cache():
    global _cache, _cache_expires_at

    _cache = None
    _cache_expires_at = 0

#!/usr/bin/env python3
"""Safe wrapper for the TouristNetTR lead machine.

The inner crawler should never make the whole GitHub Actions job fail silently.
If it crashes, this wrapper writes a crash report under reports/crashes/ and exits 0
so the Commit outputs step can preserve the evidence in the repository.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INNER_PATH = ROOT / "scripts" / "touristnettr_lead_machine.py"


def istanbul_now() -> dt.datetime:
    return dt.datetime.utcnow() + dt.timedelta(hours=3)


def write_crash_report(exc: BaseException) -> Path:
    now = istanbul_now()
    date = now.date().isoformat()
    slot = now.strftime("%H%M")
    report_dir = ROOT / "reports" / "crashes" / date / slot
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"lead_machine_crash_{date}_{slot}.md"
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    path.write_text(
        "# TouristNetTR Lead Machine Crash Report\n\n"
        f"- Date: {date}\n"
        f"- Slot: {slot}\n"
        f"- argv: `{sys.argv}`\n"
        f"- Inner script: `{INNER_PATH.relative_to(ROOT)}`\n\n"
        "## Error\n\n"
        f"```text\n{type(exc).__name__}: {exc}\n```\n\n"
        "## Traceback\n\n"
        f"```text\n{tb}\n```\n",
        encoding="utf-8",
    )
    return path


def load_inner_module():
    spec = importlib.util.spec_from_file_location("touristnettr_lead_machine_inner", INNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load inner script: {INNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        module = load_inner_module()
        result = module.main()
        return int(result or 0)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code == 0:
            return 0
        path = write_crash_report(exc)
        print(f"SAFE_WRAPPER_CAUGHT_SYSTEM_EXIT={code}")
        print(f"CRASH_REPORT={path.relative_to(ROOT)}")
        return 0
    except BaseException as exc:
        path = write_crash_report(exc)
        print(f"SAFE_WRAPPER_CAUGHT_EXCEPTION={type(exc).__name__}: {exc}")
        print(f"CRASH_REPORT={path.relative_to(ROOT)}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

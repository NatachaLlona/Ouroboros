"""Render or verify the QA plan from its single structured catalogue."""
import argparse
from qa_catalog import ROOT, load_catalog, render_plan, validate_catalog


def main():
    """Return nonzero for stale documents or catalogue/test inconsistencies."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without rewriting documentation")
    arguments = parser.parse_args()
    catalog = load_catalog()
    errors = validate_catalog(catalog)
    target = ROOT/"docs/QA_TEST_PLAN.md"
    content = render_plan(catalog)
    if arguments.check:
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            errors.append("QA_TEST_PLAN.md is stale; run scripts/generate_qa_docs.py")
    elif not errors:
        target.write_text(content, encoding="utf-8")
    for error in errors: print(error)
    print("QA catalogue and plan are consistent" if not errors else "QA consistency checks failed")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())

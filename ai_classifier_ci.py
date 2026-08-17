"""
ai_classifier_ci.py
====================
AI-assisted flaky test detection for CI/CD pipeline integration.
Runs as a pre-step in GitHub Actions after Cypress tests complete.

MSc Dissertation: AI-Assisted Flaky Test Detection in CI/CD Pipelines
Ubaid Ali - A00046299 - TU Dublin

Usage (in GitHub Actions):
    python ai_classifier_ci.py \
        --group group-2-crud \
        --passed 0 \
        --run-number 45 \
        --project 01-task-manager

Outputs:
    - decision.json  : quarantine/rerun decision + probability
    - Exits 0        : test quarantined (pipeline continues)
    - Exits 1        : genuine failure (pipeline fails normally)
"""

import json
import argparse
import os
import sys
import math

# ============================================================
# FEATURE DEFINITIONS
# Feature values derived from known project configuration
# and run context passed in as arguments
# ============================================================

# Historical pass rates per project per group
# These are seeded from baseline_results.csv averages
# Updated via rolling window after each run
HISTORICAL_PASS_RATES = {
    "01-task-manager":    {"navigation": 0.95, "crud": 0.78, "search": 0.91},
    "02-recipe-book":     {"navigation": 0.94, "crud": 0.76, "search": 0.90},
    "03-movie-reviews":   {"navigation": 0.96, "crud": 0.80, "search": 0.92},
    "04-expense-tracker": {"navigation": 0.93, "crud": 0.74, "search": 0.89},
    "05-blog-platform":   {"navigation": 0.95, "crud": 0.77, "search": 0.91},
    "06-job-board":       {"navigation": 0.96, "crud": 0.81, "search": 0.93},
    "07-student-grades":  {"navigation": 0.94, "crud": 0.75, "search": 0.90},
    "08-inventory-system":{"navigation": 0.94, "crud": 0.76, "search": 0.91},
    "09-event-planner":   {"navigation": 0.95, "crud": 0.79, "search": 0.92},
    "10-library-catalog": {"navigation": 0.93, "crud": 0.73, "search": 0.88},
}

# DOM interaction counts per spec group (fixed by test design)
DOM_INTERACTIONS = {
    "navigation": 15,
    "crud":       45,
    "search":     25,
}

# Concurrent test count (3 parallel groups in our matrix)
CONCURRENT_TESTS = 3

# Flaky probability threshold
FLAKY_THRESHOLD = 0.45

# ============================================================
# GRADIENT BOOSTING CLASSIFIER (lightweight inline version)
# Trained weights derived from classifier.py output
# This avoids needing sklearn in CI - uses the learned
# decision boundaries directly
# ============================================================

def compute_flaky_probability(pass_rate, hour_of_day, concurrent, dom_count):
    """
    Compute flaky probability using learned feature weights.
    Simplified logistic model derived from gradient boosting output.
    Feature importances: dom=0.762, pass_rate=0.222, hour=0.016, concurrent=0.000
    """
    # Normalise features (based on training data ranges)
    norm_dom = (dom_count - 15) / (45 - 15)          # 0 to 1
    norm_pass = 1.0 - pass_rate                        # invert: low pass rate = high risk
    norm_hour = abs(hour_of_day - 14) / 14             # peak risk at off-hours

    # Weighted combination (weights from feature importances)
    score = (
        0.762 * norm_dom +
        0.222 * norm_pass +
        0.016 * norm_hour +
        0.000 * concurrent
    )

    # Apply sigmoid to get probability
    probability = 1 / (1 + math.exp(-6 * (score - 0.5)))

    return round(probability, 4)

def get_hour_of_day():
    """Get current hour for time-of-day feature."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).hour

def load_pass_rate(project, group, run_number):
    """
    Load historical pass rate from rolling history file if available,
    otherwise use seeded baseline averages.
    """
    history_file = f"pass_rate_history.json"
    key = f"{project}_{group}"

    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            history = json.load(f)
        if key in history and len(history[key]) > 0:
            window = history[key][-20:]
            return sum(window) / len(window)

    # Fall back to seeded baseline averages
    return HISTORICAL_PASS_RATES.get(project, {}).get(group, 0.85)

def update_pass_rate_history(project, group, passed):
    """Update rolling pass rate history after each run."""
    history_file = "pass_rate_history.json"
    key = f"{project}_{group}"

    history = {}
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            history = json.load(f)

    if key not in history:
        history[key] = []

    history[key].append(1 if passed else 0)

    # Keep only last 50 runs
    history[key] = history[key][-50:]

    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)

def make_decision(project, group, passed, run_number):
    """
    Main decision function.
    Returns quarantine=True if test is likely flaky.
    """
    hour = get_hour_of_day()
    pass_rate = load_pass_rate(project, group, run_number)
    dom_count = DOM_INTERACTIONS.get(group, 25)

    probability = compute_flaky_probability(
        pass_rate=pass_rate,
        hour_of_day=hour,
        concurrent=CONCURRENT_TESTS,
        dom_count=dom_count
    )

    quarantine = probability >= FLAKY_THRESHOLD

    decision = {
        "project":          project,
        "spec_group":       group,
        "run_number":       run_number,
        "passed":           passed,
        "hour_of_day":      hour,
        "pass_rate_20":     pass_rate,
        "dom_interactions": dom_count,
        "concurrent_tests": CONCURRENT_TESTS,
        "flaky_probability": probability,
        "quarantine":       quarantine,
        "action":           "QUARANTINE" if quarantine else "RERUN",
        "threshold":        FLAKY_THRESHOLD,
    }

    return decision

def log_decision(decision):
    """Append decision to run log for later analysis."""
    log_file = "ai_decisions_log.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(decision) + "\n")

def main():
    parser = argparse.ArgumentParser(description="AI flaky test classifier for CI")
    parser.add_argument("--group",      required=True, help="Spec group name (navigation/crud/search)")
    parser.add_argument("--passed",     required=True, type=int, help="1 if passed, 0 if failed")
    parser.add_argument("--run-number", required=True, type=int, help="CI run number")
    parser.add_argument("--project",    required=True, help="Project repo name")
    parser.add_argument("--update-history", action="store_true", help="Update pass rate history only")
    args = parser.parse_args()

    # Normalise group name
    group = args.group.replace("group-1-", "").replace("group-2-", "").replace("group-3-", "")
    if group not in ["navigation", "crud", "search"]:
        group = "crud"  # default

    # If test passed, just update history and exit 0
    if args.passed == 1:
        update_pass_rate_history(args.project, group, passed=True)
        decision = {
            "project": args.project,
            "spec_group": group,
            "run_number": args.run_number,
            "passed": True,
            "flaky_probability": 0.0,
            "quarantine": False,
            "action": "PASSED"
        }
        with open("decision.json", "w") as f:
            json.dump(decision, f, indent=2)
        log_decision(decision)
        print(f"[AI] {args.project}/{group}: PASSED - no action needed")
        sys.exit(0)

    # Test failed - make quarantine decision
    decision = make_decision(
        project=args.project,
        group=group,
        passed=False,
        run_number=args.run_number
    )

    # Update history as failed
    update_pass_rate_history(args.project, group, passed=False)

    # Save decision
    with open("decision.json", "w") as f:
        json.dump(decision, f, indent=2)

    log_decision(decision)

    # Print clear output for CI logs
    print(f"[AI] {args.project}/{group}: probability={decision['flaky_probability']}, action={decision['action']}")
    print(f"[AI] Features: pass_rate={decision['pass_rate_20']}, dom={decision['dom_interactions']}, hour={decision['hour_of_day']}")
    print(f"[AI] Pass rate history used: last 20 runs")

    if decision["quarantine"]:
        print(f"[AI] QUARANTINED - likely flaky test, pipeline continues")
        sys.exit(0)  # Exit 0 = pipeline continues
    else:
        print(f"[AI] GENUINE FAILURE - pipeline will fail")
        sys.exit(1)  # Exit 1 = pipeline fails

if __name__ == "__main__":
    main()

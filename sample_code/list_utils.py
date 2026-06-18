# sample2_list_utils.py
# Utility functions for list processing — contains classic Python anti-patterns.
# Use this as: python main.py sample_code/sample2_list_utils.py


def remove_duplicates(items):
    """Remove duplicate values from a list."""
    result = []
    for item in items:
        # Bug: O(n²) — list.count() scans the whole list on every iteration.
        # Use a set for O(n) performance.
        if result.count(item) == 0:
            result.append(item)
    return result


def filter_negatives(numbers):
    """Remove all negative numbers from the list."""
    # Bug: modifying a list while iterating — some negatives get skipped
    for n in numbers:
        if n < 0:
            numbers.remove(n)
    return numbers


def flatten(nested, result=[]):
    """Flatten a nested list into a single list."""
    # Bug: mutable default argument — `result` is shared across all calls!
    for item in nested:
        if isinstance(item, list):
            flatten(item, result)
        else:
            result.append(item)
    return result


def top_n(items, n=10):
    """Return the top N items from a list."""
    # Bug: no check that n <= len(items) — silently returns wrong count
    items.sort(reverse=True)  # Bug: sorts the caller's list in-place (side effect)
    return items[:n]


def average(numbers):
    """Calculate the average of a list of numbers."""
    # Bug: no guard against empty list — raises ZeroDivisionError
    return sum(numbers) / len(numbers)

# Code Review Report: list_utils.py

## Executive Summary
The code health of list_utils.py is compromised due to several high-priority issues, including modifying a list while iterating over it, using mutable default arguments, and not handling empty input lists. The single most critical issue is the modification of the `numbers` list while iterating over it, which can cause items to be skipped silently. The recommended first action is to address this issue by building a separate list of items to remove.

## HIGH Priority Findings
* **Modifying a list while iterating over it**: The `numbers` list is modified while being iterated over, which can cause items to be skipped silently. This issue is found in the `filter_negatives` function.
* **Mutable default arguments**: The `flatten` function has a mutable default argument, which can lead to unexpected behavior when the function is called multiple times.
* **Not handling empty input lists**: The `average` function does not handle the case where the input list is empty, which raises a ZeroDivisionError.
* **Test coverage**: Several functions have no test for empty input, None input, or edge cases, which can lead to unexpected behavior.

## MEDIUM Priority Findings
* **Performance issues**: The `remove_duplicates` function has a time complexity of O(n²) due to the use of list.count() inside a loop, which can lead to performance issues for large lists.
* **Unexpected side effects**: The `top_n` function sorts the input list in-place, which can have unintended side effects.
* **Not checking for edge cases**: The `top_n` function does not check if n is less than or equal to the length of the list, which can lead to incorrect results.
* **Not handling non-numeric values**: The `average` function does not handle the case where the input list contains non-numeric values, which can raise a TypeError.

## LOW Priority Findings
None

## Recommended Action Plan
1. **Fix modifying a list while iterating over it**: Build a separate list of items to remove in the `filter_negatives` function.
2. **Fix mutable default arguments**: Replace the default argument with `None` and initialize the list inside the `flatten` function.
3. **Fix not handling empty input lists**: Add a check to handle the empty list case in the `average` function.
4. **Improve test coverage**: Add tests for empty input, None input, and edge cases for all functions.
5. **Fix performance issues**: Use a set to keep track of unique items in the `remove_duplicates` function.
6. **Fix unexpected side effects**: Create a copy of the list before sorting in the `top_n` function.
7. **Fix not checking for edge cases**: Add a check to ensure n is not greater than the length of the list in the `top_n` function.
8. **Fix not handling non-numeric values**: Add a check to handle non-numeric values in the `average` function.
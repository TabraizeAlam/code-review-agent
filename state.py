from typing import TypedDict, List


class Finding(TypedDict):
    severity: str
    description: str
    suggestion: str


class ReviewState(TypedDict):
    code: str
    filename: str
    bug_findings: List[Finding]
    security_findings: List[Finding]
    test_findings: List[Finding]
    final_report: str
    human_feedback: str

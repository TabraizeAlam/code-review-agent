# Code Review Report: investment_mgmt.py

## Executive Summary
The code review of investment_mgmt.py has identified several critical issues that need to be addressed to ensure the security, reliability, and maintainability of the code. The most critical issue is the hardcoded credentials for database, Bloomberg API, and custodian token, which poses a significant security risk. The recommended first action is to store these credentials securely using environment variables or a secrets management system.

## HIGH Priority Findings
* **Security Risks**:
	+ Hardcoded credentials for database, Bloomberg API, and custodian token ( Bug #1, Security #1)
	+ SQL injection vulnerabilities in get_portfolio, execute_trade, and generate_performance_report functions (Bug #2, Security #2, #3, #4)
	+ Resource leaks due to unclosed database connections in get_portfolio, execute_trade, and generate_performance_report functions (Bug #3, Security #6)
	+ Potential TypeError in calculate_portfolio_value function if get_market_price returns None (Bug #4)
	+ No validation for quantity and price in execute_trade function (Bug #5, Security #5)
	+ No status code check in get_market_price function (Bug #6)
* **Test Coverage**:
	+ get_portfolio() has no test for SQL injection vulnerability (Test #1)
	+ calculate_portfolio_value() has no test for None price from get_market_price() (Test #2)
	+ get_market_price() has no test for API failure (Test #3)

## MEDIUM Priority Findings
* **Security Risks**:
	+ Missing input validation for quantity and price in execute_trade function (Security #5)
	+ Sensitive data exposure due to trade logs being written to a plain text file (Security #7)
	+ Internal API token is hardcoded and included in every payload in send_report_to_client function (Security #8)
* **Bug Fixes**:
	+ Potential KeyError in rebalance_portfolio function if ticker is not in holdings (Bug #7)
	+ Potential division by zero error in generate_performance_report function (Bug #8)
	+ No response status code check in send_report_to_client function (Bug #9)
	+ Potential ZeroDivisionError in check_concentration_limit function if total portfolio value is zero (Bug #10)
* **Test Coverage**:
	+ execute_trade() has no test for negative quantity (Test #4)
	+ execute_trade() has no test for zero price (Test #5)
	+ rebalance_portfolio() has no test for KeyError when ticker is not in holdings (Test #6)
	+ generate_performance_report() has no test for division by zero when total_bought is 0 (Test #7)
	+ check_concentration_limit() has no test for ZeroDivisionError when total is 0 (Test #8)

## LOW Priority Findings
* **Bug Fixes**:
	+ List is mutated while iterating in check_concentration_limit function (Bug #11)
	+ Internal API token is hardcoded and included in every payload in send_report_to_client function (Bug #12)
* **Test Coverage**:
	+ get_portfolio() has no test for empty client_id (Test #9)
	+ calculate_portfolio_value() has no test for empty holdings (Test #10)
	+ get_market_price() has no test for empty ticker (Test #11)
	+ execute_trade() has no test for empty client_id (Test #12)
	+ rebalance_portfolio() has no test for empty target_weights (Test #13)
	+ generate_performance_report() has no test for empty trades (Test #14)
	+ check_concentration_limit() has no test for empty holdings (Test #15)

## Recommended Action Plan
1. Store hardcoded credentials securely using environment variables or a secrets management system.
2. Fix SQL injection vulnerabilities in get_portfolio, execute_trade, and generate_performance_report functions by using parameterized queries.
3. Close database connections after use to prevent resource leaks.
4. Add error handling to calculate_portfolio_value function to handle None values from get_market_price.
5. Add input validation to execute_trade function to ensure quantity and price are valid and non-negative.
6. Add status code checks to get_market_price and send_report_to_client functions to handle API failures and exceptions.
7. Write tests for get_portfolio, calculate_portfolio_value, and get_market_price functions to cover SQL injection vulnerabilities, None prices, and API failures.
8. Fix potential KeyErrors, division by zero errors, and ZeroDivisionErrors in rebalance_portfolio, generate_performance_report, and check_concentration_limit functions.
9. Add tests for execute_trade, rebalance_portfolio, generate_performance_report, and check_concentration_limit functions to cover negative quantities, zero prices, KeyErrors, and division by zero errors.
10. Refactor check_concentration_limit function to avoid mutating the list while iterating.
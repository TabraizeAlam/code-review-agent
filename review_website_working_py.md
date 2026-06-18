# Code Review Report: website_working.py

## Executive Summary
The code review of website_working.py has identified several issues that need to be addressed to ensure the overall health and security of the application. The most critical issue is the lack of validation for existing usernames and emails in the register function, which could lead to duplicate usernames or emails. The recommended first action is to add checks to prevent duplicate usernames or emails in the register function.

## HIGH Priority Findings
* The register function does not check for existing usernames before creating a new user, which could lead to duplicate usernames. (Test Coverage)
* The delete_user function does not check if the user to be deleted is the same as the current user, which could lead to accidental self-deletion. (Test Coverage)

## MEDIUM Priority Findings
* The database connection is not explicitly closed in the get_db function. (Bug Review)
* The delete_user function does not check if the user to be deleted is the same as the currently logged-in user. (Bug Review)
* The register function does not check if the username or email already exists. (Bug Review)
* The /upload route does not validate the file contents, which could lead to uploading malicious files. (Security Review)
* The /admin/delete_user route does not confirm the deletion of a user, which could lead to accidental deletions. (Security Review)
* The login function does not handle the case where the username or password is None. (Test Coverage)
* The search function does not handle the case where the search term is None or empty. (Test Coverage)
* The submit_trade function does not handle the case where the quantity is a very large number. (Test Coverage)
* The admin_users function does not handle the case where there are no users in the database. (Test Coverage)
* The dashboard function does not handle the case where the user has no portfolios. (Test Coverage)

## LOW Priority Findings
* The upload folder path is not defined anywhere in the code. (Bug Review)
* The search function does not limit the number of results returned. (Bug Review)
* The /register route does not validate if the username or email already exists in the database before creating a new user. (Security Review)
* The /login route does not limit the number of login attempts, making it vulnerable to brute-force attacks. (Security Review)
* The upload_file function does not handle the case where the file is too large. (Test Coverage)

## Recommended Action Plan
1. Add checks to prevent duplicate usernames or emails in the register function.
2. Implement a check to prevent a user from deleting their own account in the delete_user function.
3. Explicitly close the database connection in the get_db function.
4. Validate the file contents in the /upload route to prevent uploading malicious files.
5. Add a confirmation step before deleting a user in the /admin/delete_user route.
6. Handle the case where the username or password is None in the login function.
7. Handle the case where the search term is None or empty in the search function.
8. Handle the case where the quantity is a very large number in the submit_trade function.
9. Define the upload folder path.
10. Limit the number of results returned in the search function.
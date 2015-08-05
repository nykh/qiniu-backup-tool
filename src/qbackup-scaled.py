__author__ = 'nykh'

"""
scalable version of qbackup.

In real test cases where there are tens of thousands of files online, we found out it is not
practical to pull the full list of files into RAM (it can take hours).
"""


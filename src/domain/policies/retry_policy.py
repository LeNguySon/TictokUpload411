"""
Retry Policy providing exponential backoff with full jitter and deterministic error classification.
"""

import random
import re
from enum import StrEnum


class ErrorClassification(StrEnum):
    NON_RETRYABLE_AUTH = "non_retryable_auth"
    NON_RETRYABLE_ACCOUNT = "non_retryable_account"
    NON_RETRYABLE_CONTENT = "non_retryable_content"
    RETRYABLE_NETWORK = "retryable_network"
    RETRYABLE_SERVER = "retryable_server"
    UNKNOWN = "unknown"


class RetryPolicy:
    """
    Evaluates whether an upload or network operation should be retried,
    and computes delay with exponential backoff and jitter.
    """

    NON_RETRYABLE_AUTH_PATTERNS = [
        r"401",
        r"unauthorized",
        r"token.*expired",
        r"invalid.*token",
        r"scope",
    ]

    NON_RETRYABLE_ACCOUNT_PATTERNS = [
        r"checkpoint",
        r"banned",
        r"suspended",
        r"cookie.*dead",
        r"verification.*required",
    ]

    NON_RETRYABLE_CONTENT_PATTERNS = [
        r"copyright",
        r"community.*guidelines",
        r"policy.*violation",
        r"video.*format.*invalid",
    ]

    RETRYABLE_NETWORK_PATTERNS = [
        r"429",
        r"rate.*limit",
        r"timeout",
        r"timed.*out",
        r"connection.*reset",
        r"502",
        r"503",
        r"504",
        r"bad.*gateway",
        r"gateway.*timeout",
    ]

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_sec: float = 1.0,
        max_delay_sec: float = 30.0,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay_sec = base_delay_sec
        self.max_delay_sec = max_delay_sec

    def classify_error(self, error_message: str) -> ErrorClassification:
        msg = error_message.lower()

        for pat in self.NON_RETRYABLE_AUTH_PATTERNS:
            if re.search(pat, msg):
                return ErrorClassification.NON_RETRYABLE_AUTH

        for pat in self.NON_RETRYABLE_ACCOUNT_PATTERNS:
            if re.search(pat, msg):
                return ErrorClassification.NON_RETRYABLE_ACCOUNT

        for pat in self.NON_RETRYABLE_CONTENT_PATTERNS:
            if re.search(pat, msg):
                return ErrorClassification.NON_RETRYABLE_CONTENT

        for pat in self.RETRYABLE_NETWORK_PATTERNS:
            if re.search(pat, msg):
                return ErrorClassification.RETRYABLE_NETWORK

        return ErrorClassification.UNKNOWN

    def should_retry(self, attempt: int, error: str) -> bool:
        if attempt >= self.max_retries:
            return False

        classification = self.classify_error(error)
        if classification in (
            ErrorClassification.NON_RETRYABLE_AUTH,
            ErrorClassification.NON_RETRYABLE_ACCOUNT,
            ErrorClassification.NON_RETRYABLE_CONTENT,
        ):
            return False

        return True

    def get_delay_seconds(self, attempt: int) -> float:
        # Full jitter exponential backoff: Uniform(0, min(max_delay, base * 2^attempt)) + base
        exponential = self.base_delay_sec * (2**attempt)
        capped = min(self.max_delay_sec, exponential)
        jitter = random.uniform(0.0, 1.0)
        return capped + jitter

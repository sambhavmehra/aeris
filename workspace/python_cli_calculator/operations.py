import math

class ArithmeticOperationError(Exception):
    """Base class for arithmetic operation exceptions."""
    pass

class DivisionByZeroError(ArithmeticOperationError):
    """Raised when attempting division by zero."""
    pass


def add(num1: float, num2: float) -> float:
    """Returns the sum of two numbers."""
    return num1 + num2


def subtract(num1: float, num2: float) -> float:
    """Returns the difference between two numbers."""
    return num1 - num2


def multiply(num1: float, num2: float) -> float:
    """Returns the product of two numbers."""
    return num1 * num2


def divide(num1: float, num2: float) -> float:
    """Returns the quotient of two numbers, raising an exception if dividing by zero."""
    if num2 == 0:
        raise DivisionByZeroError("Cannot divide by zero.")
    return num1 / num2

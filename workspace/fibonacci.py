from typing import Union

def calculate_fibonacci(n: int) -> Union[int, None]:
    """
    Calculate the nth Fibonacci number.

    Args:
        n (int): The position of the Fibonacci number to calculate.

    Returns:
        Union[int, None]: The nth Fibonacci number if n is a non-negative integer, otherwise None.

    Raises:
        TypeError: If n is not an integer.
        ValueError: If n is a negative integer.
    """
    # Input validation
    if not isinstance(n, int):
        raise TypeError("Input must be an integer.")
    if n < 0:
        raise ValueError("Input must be a non-negative integer.")

    # Base cases
    if n == 0:
        return 0
    elif n == 1:
        return 1

    # Initialize variables
    a, b = 0, 1

    # Calculate the nth Fibonacci number
    for _ in range(2, n + 1):
        a, b = b, a + b

    return b

def main():
    try:
        n = int(input("Enter the position of the Fibonacci number to calculate: "))
        result = calculate_fibonacci(n)
        if result is not None:
            print(f"The {n}th Fibonacci number is: {result}")
    except (TypeError, ValueError) as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
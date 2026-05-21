def is_prime(n: int) -> bool:
    """
    Checks if a number is prime.

    Args:
        n (int): The number to check.

    Returns:
        bool: True if the number is prime, False otherwise.
    """
    if n <= 1:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    max_divisor = int(n**0.5) + 1
    for d in range(3, max_divisor, 2):
        if n % d == 0:
            return False
    return True

def main() -> None:
    """
    Asks the user for a number and checks if it's prime.
    """
    while True:
        try:
            num = int(input("Enter a number: "))
            if is_prime(num):
                print(f"{num} is a prime number.")
            else:
                print(f"{num} is not a prime number.")
        except ValueError:
            print("Invalid input. Please enter a whole number.")

if __name__ == "__main__":
    main()
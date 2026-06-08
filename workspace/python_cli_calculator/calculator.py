import argparse
import math
from operations import add, subtract, multiply, divide
from utils import get_user_input, display_result


def main():
    parser = argparse.ArgumentParser(description='Python CLI Calculator')
    parser.add_argument('--num1', type=float, help='First number')
    parser.add_argument('--num2', type=float, help='Second number')
    parser.add_argument('--operation', type=str, help='Arithmetic operation (+, -, *, /)')
    args = parser.parse_args()

    if args.num1 is None or args.num2 is None or args.operation is None:
        num1 = get_user_input('Enter the first number: ')
        num2 = get_user_input('Enter the second number: ')
        operation = get_user_input('Enter the operation (+, -, *, /): ')
    else:
        num1 = args.num1
        num2 = args.num2
        operation = args.operation

    if operation == '+':
        result = add(num1, num2)
    elif operation == '-':
        result = subtract(num1, num2)
    elif operation == '*':
        result = multiply(num1, num2)
    elif operation == '/':
        if num2 != 0:
            result = divide(num1, num2)
        else:
            raise ZeroDivisionError('Cannot divide by zero')
    else:
        raise ValueError('Invalid operation')

    display_result(result)

if __name__ == '__main__':
    main()
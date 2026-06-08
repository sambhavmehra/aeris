import argparse
import math
from pathlib import Path
from dataclasses import dataclass
from typing import Union

@dataclass
class CalculatorError(Exception):
    message: str

    def __str__(self):
        return self.message

def get_user_input(prompt: str) -> str:
    while True:
        try:
            user_input = input(prompt)
            if user_input:
                return user_input
            else:
                print("Please enter a valid input.")
        except KeyboardInterrupt:
            print("\nExiting program.")
            exit(0)
        except Exception as e:
            print(f"An error occurred: {str(e)}")

def validate_input(input_str: str) -> Union[float, int]:
    try:
        if "." in input_str:
            return float(input_str)
        else:
            return int(input_str)
    except ValueError:
        raise CalculatorError("Invalid input. Please enter a number.")

def display_result(result: Union[float, int]) -> None:
    print(f"Result: {result}")

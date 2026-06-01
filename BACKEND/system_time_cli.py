import datetime
import time

def display_time():
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"Current Time: {current_time}")

def main():
    while True:
        display_time()
        time.sleep(1)

if __name__ == "__main__":
    main()
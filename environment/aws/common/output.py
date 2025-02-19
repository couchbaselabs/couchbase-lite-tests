from termcolor import colored


def header(text: str):
    print()
    print(colored(f"=== {text} ===", "green"))
    print()
